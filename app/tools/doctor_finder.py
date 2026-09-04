"""Find nearby hospitals and clinics via OpenStreetMap.

Nominatim geocodes the patient's location; Overpass returns healthcare
facilities around it. The main Overpass instance is frequently overloaded,
so several mirrors are tried before reporting no results.
"""

import math
import time

import requests

from app.logging_config import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

HEADERS = {"User-Agent": "AgenticMedicalAssistant/1.0"}

GEOCODE_TIMEOUT = 15
OVERPASS_TIMEOUT = 25
MAX_RESULTS = 8


class LookupFailed(RuntimeError):
    """Every upstream provider failed. Distinct from 'no results here'."""


def _geocode_location(location: str):

    location = (location or "").strip()

    if len(location) < 3:
        return None, None

    params = {"q": location, "format": "json", "limit": 1, "countrycodes": "in"}

    for attempt in range(2):
        try:
            response = requests.get(
                NOMINATIM_URL, params=params, headers=HEADERS, timeout=GEOCODE_TIMEOUT
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                return None, None

            return float(results[0]["lat"]), float(results[0]["lon"])

        except Exception as error:
            logger.warning(
                "Geocoding attempt failed",
                extra={"attempt": attempt + 1, "error_type": type(error).__name__},
            )
            time.sleep(1)

    return None, None


def _run_overpass_query(lat, lng, radius_meters):

    query = f"""
    [out:json][timeout:20];
    (
      nwr["amenity"="hospital"](around:{radius_meters},{lat},{lng});
      nwr["amenity"="clinic"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="hospital"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="clinic"](around:{radius_meters},{lat},{lng});
      nwr["healthcare"="doctor"](around:{radius_meters},{lat},{lng});
    );
    out center 15;
    """

    last_error = None

    for mirror in OVERPASS_MIRRORS:
        try:
            response = requests.post(
                mirror, data={"data": query}, headers=HEADERS, timeout=OVERPASS_TIMEOUT
            )
            response.raise_for_status()
            return response.json()

        except Exception as error:
            last_error = error
            logger.warning(
                "Overpass mirror failed",
                extra={"mirror": mirror, "error_type": type(error).__name__},
            )

    raise LookupFailed(f"All Overpass mirrors failed: {last_error}")


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
    """

    if not location or not location.strip():
        return []

    lat, lng = _geocode_location(location)

    if lat is None:
        logger.info("Location could not be geocoded")
        return []

    elements = []
    all_mirrors_failed = True

    for radius in (radius_meters, radius_meters * 2, radius_meters * 4):
        try:
            data = _run_overpass_query(lat, lng, radius)
            all_mirrors_failed = False
        except LookupFailed:
            time.sleep(2)
            continue

        elements = data.get("elements", [])

        if elements:
            break

    if all_mirrors_failed:
        raise LookupFailed("Could not reach the facility directory.")

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

    logger.info("Facility lookup complete", extra={"results": len(results)})

    return results[:MAX_RESULTS]
