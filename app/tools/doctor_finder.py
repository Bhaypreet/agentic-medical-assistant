import time
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# multiple free Overpass mirrors - the main one (overpass-api.de) is
# frequently overloaded, so we fall back to alternates instead of
# reporting "no hospitals found" when it's actually just a server issue
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

HEADERS = {
    "User-Agent": "AgenticMedicalAssistant/1.0 (student portfolio project)"
}


def _geocode_location(location: str):

    location = location.strip()

    if len(location) < 3:
        return None, None

    params = {
        "q": location,
        "format": "json",
        "limit": 1,
        "countrycodes": "in"
    }

    for attempt in range(2):
        try:
            response = requests.get(
                NOMINATIM_URL,
                params=params,
                headers=HEADERS,
                timeout=15
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                return None, None

            return float(results[0]["lat"]), float(results[0]["lon"])

        except Exception as e:
            print(f"Geocoding attempt {attempt + 1} failed: {e}")
            time.sleep(1)

    return None, None


def _run_overpass_query(lat, lng, radius_meters):

    overpass_query = f"""
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
                mirror,
                data={"data": overpass_query},
                headers=HEADERS,
                timeout=20
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            last_error = e
            print(f"Overpass mirror failed ({mirror}): {e}")
            continue

    raise Exception(f"All Overpass mirrors failed. Last error: {last_error}")


def find_doctors(location: str, specialist: str, radius_meters: int = 8000):

    if not location or not location.strip():
        return []

    lat, lng = _geocode_location(location)

    if lat is None:
        return []

    elements = []

    for radius in (radius_meters, radius_meters * 2, radius_meters * 4):

        try:
            data = _run_overpass_query(lat, lng, radius)
        except Exception as e:
            print(f"Overpass error at radius {radius}: {e}")
            # server-side failure, not "genuinely no results" - try a
            # slightly longer pause before the next radius/mirror attempt
            time.sleep(2)
            continue

        elements = data.get("elements", [])

        if elements:
            break

    if not elements:
        return []

    doctors = []

    for element in elements[:8]:

        tags = element.get("tags", {})
        name = tags.get("name")

        if not name:
            continue

        if "lat" in element and "lon" in element:
            point_lat = element["lat"]
            point_lng = element["lon"]
        else:
            center = element.get("center", {})
            point_lat = center.get("lat")
            point_lng = center.get("lon")

        if point_lat is None:
            continue

        address_parts = [
            tags.get("addr:housenumber", ""),
            tags.get("addr:street", ""),
            tags.get("addr:city", location)
        ]
        address = ", ".join(p for p in address_parts if p) or location

        doctors.append({
            "name": name,
            "rating": "N/A",
            "address": address,
            "location": {"lat": point_lat, "lng": point_lng}
        })

    return doctors