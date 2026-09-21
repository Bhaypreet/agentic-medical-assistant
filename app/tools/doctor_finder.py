"""Find nearby hospitals and clinics via OpenStreetMap.

Nominatim geocodes the patient's location; Overpass returns healthcare
facilities around it. The main Overpass instance is frequently overloaded,
so several mirrors are tried before reporting no results.
"""

import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout

import requests

from app.logging_config import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Mirrors are raced in parallel, not tried in turn: probed from India, only
# the main instance answered (in ~8s) while every other mirror hung until
# its timeout. Tried one after another, a slow main instance cost ~75s per
# search radius and ~225s over three radii - past gunicorn's 120s worker
# timeout and the frontend's 60s read timeout, so the patient got an error
# instead of hospitals. overpass.openstreetmap.ru refuses connections
# outright and is gone.
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {"User-Agent": "AgenticMedicalAssistant/1.0"}

# The whole lookup - geocoding plus every Overpass attempt - has to finish
# well inside the frontend's 60s read timeout, or a correct answer arrives
# after the patient has already been shown an error.
LOOKUP_BUDGET = 30
GEOCODE_TIMEOUT = 8
OVERPASS_TIMEOUT = 20

# Overpass gives the richest answer - clinics, practices, phone numbers -
# but the public instances throttle shared cloud egress. From Render every
# mirror failed for every city: the main instance rejected in ~3s and the
# rest hung. So it gets a short leash, and Nominatim is the fallback.
OVERPASS_BUDGET = 10
MAX_RESULTS = 8

# Cities are asked about over and over; Nominatim's usage policy also asks
# clients not to repeat identical queries.
_GEOCODE_CACHE: dict[str, tuple[float, float]] = {}


class LookupFailed(RuntimeError):
    """Every upstream provider failed. Distinct from 'no results here'."""


def _remaining(deadline: float) -> float:
    return deadline - time.monotonic()


def _geocode_location(location: str, deadline: float | None = None):

    location = (location or "").strip()

    if len(location) < 3:
        return None, None

    key = location.lower()

    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    deadline = deadline or time.monotonic() + LOOKUP_BUDGET
    params = {"q": location, "format": "json", "limit": 1, "countrycodes": "in"}

    for attempt in range(2):
        timeout = min(GEOCODE_TIMEOUT, _remaining(deadline))

        if timeout <= 1:
            break

        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            results = response.json()

            if not results:
                return None, None

            point = float(results[0]["lat"]), float(results[0]["lon"])
            _GEOCODE_CACHE[key] = point

            return point

        except Exception as error:
            logger.warning(
                "Geocoding attempt failed",
                extra={"attempt": attempt + 1, "error_type": type(error).__name__},
            )

    return None, None


def _overpass_query(lat, lng, radius_meters) -> str:
    return f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    (
      nwr["amenity"="hospital"](around:{radius_meters},{lat},{lng});
      nwr["amenity"="clinic"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="hospital"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="clinic"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="doctor"](around:{radius_meters},{lat},{lng});
    );
    out center 15;
    """


def _ask_mirror(mirror: str, query: str, timeout: float) -> dict:
    response = requests.post(mirror, data={"data": query}, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _run_overpass_query(lat, lng, radius_meters, deadline: float | None = None):
    """Race every mirror; the first good answer wins.

    Losers are abandoned rather than awaited - waiting for them is exactly
    the cost this exists to avoid.
    """

    deadline = deadline or time.monotonic() + LOOKUP_BUDGET
    timeout = min(OVERPASS_TIMEOUT, _remaining(deadline))

    if timeout <= 1:
        raise LookupFailed("No time left to query the facility directory.")

    query = _overpass_query(lat, lng, radius_meters)
    pool = ThreadPoolExecutor(max_workers=len(OVERPASS_MIRRORS))
    last_error = None

    try:
        futures = {pool.submit(_ask_mirror, m, query, timeout): m for m in OVERPASS_MIRRORS}

        try:
            for future in as_completed(futures, timeout=timeout + 1):
                try:
                    return future.result()
                except Exception as error:
                    last_error = error
                    status = getattr(getattr(error, "response", None), "status_code", "")
                    logger.warning(
                        f"Overpass mirror failed: {futures[future]} "
                        f"{type(error).__name__} {status}".rstrip()
                    )
        except FuturesTimeout:
            last_error = TimeoutError("no mirror answered in time")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    raise LookupFailed(f"All Overpass mirrors failed: {last_error}")


def _nominatim_facilities(lat, lng, radius_meters, deadline: float) -> list[dict] | None:
    """Hospitals near a point from Nominatim, shaped like Overpass elements.

    Coarser than Overpass - mostly hospitals, fewer clinics, rarely a
    phone number - but it is the same service that geocodes the location,
    so it is reachable from anywhere geocoding is.
    """

    half_lat = radius_meters / 111_000
    half_lng = radius_meters / (111_000 * max(math.cos(math.radians(lat)), 0.1))

    elements = []
    answered = False

    for term in ("hospital", "clinic"):
        timeout = min(GEOCODE_TIMEOUT, _remaining(deadline))

        if timeout <= 1 or len(elements) >= MAX_RESULTS:
            break

        # Nominatim's usage policy is at most one request a second.
        time.sleep(1)

        try:
            response = requests.get(
                NOMINATIM_URL,
                params={
                    "q": term,
                    "format": "jsonv2",
                    "limit": 15,
                    "bounded": 1,
                    "countrycodes": "in",
                    "viewbox": f"{lng - half_lng},{lat + half_lat},{lng + half_lng},{lat - half_lat}",
                    "extratags": 1,
                    "addressdetails": 1,
                },
                headers=HEADERS,
                timeout=timeout,
            )
            response.raise_for_status()
            found = response.json()
            answered = True
        except Exception as error:
            logger.warning(f"Nominatim facility search failed: {type(error).__name__}")
            continue

        for place in found if isinstance(found, list) else []:
            address = place.get("address") or {}
            extra = place.get("extratags") or {}

            try:
                point_lat, point_lng = float(place["lat"]), float(place["lon"])
            except (KeyError, TypeError, ValueError):
                continue

            elements.append(
                {
                    "lat": point_lat,
                    "lon": point_lng,
                    "tags": {
                        "name": place.get("name") or "",
                        "phone": extra.get("phone") or extra.get("contact:phone") or "",
                        "addr:housenumber": address.get("house_number", ""),
                        "addr:street": address.get("road", ""),
                        "addr:city": address.get("city")
                        or address.get("town")
                        or address.get("village")
                        or address.get("state_district", ""),
                    },
                }
            )

    return elements if answered else None


def _distance_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance, used in place of the rating OSM does not have."""

    radius = 6371.0

    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2
    )

    return round(radius * 2 * math.asin(math.sqrt(a)), 1)


def _coordinates_of(element):

    if "lat" in element and "lon" in element:
        return element["lat"], element["lon"]

    center = element.get("center", {})

    return center.get("lat"), center.get("lon")


def find_doctors(location: str, specialist: str, radius_meters: int = 8000) -> list[dict]:
    """Healthcare facilities near a location, nearest first.

    Returns an empty list when the location cannot be geocoded or nothing
    is nearby. Raises LookupFailed when every upstream provider failed, so
    the caller can distinguish "nothing here" from "we could not check".
    Never runs longer than LOOKUP_BUDGET.
    """

    if not location or not location.strip():
        return []

    deadline = time.monotonic() + LOOKUP_BUDGET

    lat, lng = _geocode_location(location, deadline)

    if lat is None:
        logger.info("Location could not be geocoded")
        return []

    elements = []
    reached = False
    overpass_deadline = min(deadline, time.monotonic() + OVERPASS_BUDGET)

    # One wider retry for sparse towns - but only if Overpass answered at
    # all. A mirror that refused us will refuse the wider query too.
    for radius in (radius_meters, radius_meters * 3):
        if _remaining(overpass_deadline) <= 2:
            break

        try:
            elements = _run_overpass_query(lat, lng, radius, overpass_deadline).get("elements", [])
            reached = True
        except LookupFailed:
            break

        if elements:
            break

    if not elements:
        fallback = _nominatim_facilities(lat, lng, radius_meters * 2, deadline)

        # "Nothing near you" and "we could not check" must stay distinct,
        # so a patient is never told there are no hospitals when neither
        # source could be asked.
        if fallback is None and not reached:
            raise LookupFailed("Could not reach the facility directory.")

        elements = fallback or []

    results = []

    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")

        if not name:
            continue

        point_lat, point_lng = _coordinates_of(element)

        if point_lat is None or point_lng is None:
            continue

        address_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", location),
        ]

        results.append(
            {
                "name": name,
                "address": ", ".join(part for part in address_parts if part) or location,
                # OSM has no ratings, so the previous hardcoded "N/A"
                # rating was a field that could never hold a value.
                # Distance is something the source actually provides.
                "distance_km": _distance_km(lat, lng, point_lat, point_lng),
                "phone": tags.get("phone") or tags.get("contact:phone") or "",
                "location": {"lat": point_lat, "lng": point_lng},
            }
        )

    results.sort(key=lambda item: item["distance_km"])

    # The same facility arrives more than once - mapped as both a building
    # and a site, or matched by both the "hospital" and "clinic" searches.
    # Listing it twice pushes a real alternative off the end of the list.
    unique = []

    for item in results:
        name = " ".join(item["name"].casefold().split())

        if any(
            " ".join(kept["name"].casefold().split()) == name
            and abs(kept["distance_km"] - item["distance_km"]) < 0.5
            for kept in unique
        ):
            continue

        unique.append(item)

    results = unique

    logger.info("Facility lookup complete", extra={"results": len(results)})

    return results[:MAX_RESULTS]
