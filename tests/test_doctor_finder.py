from unittest.mock import MagicMock, patch

import pytest

from app.tools import doctor_finder
from app.tools.doctor_finder import LookupFailed, find_doctors


@pytest.fixture(autouse=True)
def _fresh_geocode_cache():
    """The cache would otherwise let one test's geocode answer another's."""

    doctor_finder._GEOCODE_CACHE.clear()
    yield
    doctor_finder._GEOCODE_CACHE.clear()


def _geocode(lat="30.9", lon="75.8"):
    response = MagicMock()
    response.json.return_value = [{"lat": lat, "lon": lon}]
    response.raise_for_status.return_value = None
    return response


def _overpass(elements):
    response = MagicMock()
    response.json.return_value = {"elements": elements}
    response.raise_for_status.return_value = None
    return response


@patch("app.tools.doctor_finder.requests.post")
@patch("app.tools.doctor_finder.requests.get")
def test_returns_parsed_results(mock_get, mock_post):

    mock_get.return_value = _geocode()
    mock_post.return_value = _overpass(
        [{"tags": {"name": "Test Hospital", "addr:city": "Ludhiana"}, "lat": 30.9, "lon": 75.8}]
    )

    results = find_doctors("Ludhiana", "hospital")

    assert len(results) == 1
    assert results[0]["name"] == "Test Hospital"
    assert results[0]["location"]["lat"] == 30.9


@patch("app.tools.doctor_finder.requests.post")
@patch("app.tools.doctor_finder.requests.get")
def test_results_carry_distance_not_a_placeholder_rating(mock_get, mock_post):

    mock_get.return_value = _geocode("30.90", "75.80")
    mock_post.return_value = _overpass(
        [{"tags": {"name": "Near Clinic"}, "lat": 30.91, "lon": 75.80}]
    )

    result = find_doctors("Ludhiana", "hospital")[0]

    # OSM has no ratings; the old hardcoded "N/A" was rendered to users.
    assert "rating" not in result
    assert 0 < result["distance_km"] < 5


@patch("app.tools.doctor_finder.requests.post")
@patch("app.tools.doctor_finder.requests.get")
def test_results_are_sorted_nearest_first(mock_get, mock_post):

    mock_get.return_value = _geocode("30.90", "75.80")
    mock_post.return_value = _overpass(
        [
            {"tags": {"name": "Far"}, "lat": 31.20, "lon": 75.80},
            {"tags": {"name": "Near"}, "lat": 30.91, "lon": 75.80},
        ]
    )

    names = [item["name"] for item in find_doctors("Ludhiana", "hospital")]

    assert names == ["Near", "Far"]


@patch("app.tools.doctor_finder.requests.post")
@patch("app.tools.doctor_finder.requests.get")
def test_elements_without_a_name_or_coordinates_are_skipped(mock_get, mock_post):

    mock_get.return_value = _geocode()
    mock_post.return_value = _overpass(
        [
            {"tags": {}, "lat": 30.9, "lon": 75.8},
            {"tags": {"name": "No coords"}},
            {"tags": {"name": "Centre only"}, "center": {"lat": 30.92, "lon": 75.81}},
        ]
    )

    results = find_doctors("Ludhiana", "hospital")

    assert [item["name"] for item in results] == ["Centre only"]


@patch("app.tools.doctor_finder.requests.get")
def test_unknown_location_returns_empty(mock_get):

    response = MagicMock()
    response.json.return_value = []
    response.raise_for_status.return_value = None
    mock_get.return_value = response

    assert find_doctors("asdkfjaslkdjf", "hospital") == []


def test_blank_location_returns_empty():
    assert find_doctors("", "hospital") == []
    assert find_doctors("   ", "hospital") == []


@patch("app.tools.doctor_finder.time.sleep")
@patch("app.tools.doctor_finder.requests.post", side_effect=OSError("network down"))
@patch("app.tools.doctor_finder.requests.get")
def test_every_source_failing_raises_rather_than_reporting_no_results(mock_get, _post, _sleep):

    # Geocoding works; Overpass and Nominatim's facility search both fail.
    mock_get.side_effect = [_geocode(), OSError("down"), OSError("down")]

    # "we could not check" must be distinguishable from "nothing nearby",
    # so the caller can say so instead of telling a patient there are no
    # hospitals near them.
    with pytest.raises(LookupFailed):
        find_doctors("Ludhiana", "hospital")


def _nominatim(places):
    response = MagicMock()
    response.json.return_value = places
    response.raise_for_status.return_value = None
    return response


@patch("app.tools.doctor_finder.time.sleep")
@patch("app.tools.doctor_finder.requests.post", side_effect=OSError("429 from a shared cloud IP"))
@patch("app.tools.doctor_finder.requests.get")
def test_overpass_being_unreachable_falls_back_to_nominatim(mock_get, _post, _sleep):
    """What production hit: every Overpass mirror refused Render, so every
    city came back as "couldn't reach the hospital directory"."""

    mock_get.side_effect = [
        _geocode("30.9661", "76.5231"),
        _nominatim(
            [
                {
                    "name": "Civil Hospital Ropar",
                    "lat": "30.9700",
                    "lon": "76.5300",
                    "address": {"road": "Hospital Road", "city": "Rupnagar"},
                    "extratags": {"phone": "+91 1881 222222"},
                }
            ]
        ),
        _nominatim([]),
    ]

    results = find_doctors("Ropar", "hospital")

    assert [r["name"] for r in results] == ["Civil Hospital Ropar"]
    assert results[0]["phone"] == "+91 1881 222222"
    assert "Hospital Road" in results[0]["address"]
    assert results[0]["distance_km"] < 5


@patch("app.tools.doctor_finder.time.sleep")
@patch("app.tools.doctor_finder.requests.post", side_effect=OSError("down"))
@patch("app.tools.doctor_finder.requests.get")
def test_an_empty_fallback_means_nothing_nearby_not_unreachable(mock_get, _post, _sleep):
    mock_get.side_effect = [_geocode(), _nominatim([]), _nominatim([])]

    assert find_doctors("Tiny Village", "hospital") == []


def test_the_whole_lookup_is_time_bounded():
    """It has to finish inside the frontend's 60s read timeout."""

    assert doctor_finder.LOOKUP_BUDGET < 60
    assert doctor_finder.OVERPASS_BUDGET < doctor_finder.LOOKUP_BUDGET


@patch("app.tools.doctor_finder.time.sleep")
@patch("app.tools.doctor_finder.requests.post", side_effect=OSError("down"))
@patch("app.tools.doctor_finder.requests.get")
def test_the_same_facility_is_listed_once(mock_get, _post, _sleep):
    same = {"name": "Civil Hospital Ropar", "lat": "30.9670", "lon": "76.5235", "address": {}}
    near_twin = {"name": "civil hospital  ropar", "lat": "30.9672", "lon": "76.5236", "address": {}}
    other = {"name": "Pannu Hospital", "lat": "30.9700", "lon": "76.5300", "address": {}}

    mock_get.side_effect = [
        _geocode("30.9661", "76.5231"),
        _nominatim([same, other]),
        _nominatim([near_twin]),
    ]

    names = [r["name"] for r in find_doctors("Ropar", "hospital")]

    assert names.count("Civil Hospital Ropar") == 1
    assert "civil hospital  ropar" not in names
    assert "Pannu Hospital" in names


@patch("app.tools.doctor_finder.time.sleep")
@patch("app.tools.doctor_finder.requests.get")
def test_a_hanging_overpass_does_not_hold_back_a_nominatim_answer(mock_get, _sleep):
    """On Render every mirror hangs; waiting them out made each search ~14s."""

    import time as real_time

    def hang(*_args, **_kwargs):
        real_time.sleep(5)
        raise OSError("timed out")

    mock_get.side_effect = [
        _geocode(),
        _nominatim([{"name": "City Hospital", "lat": "30.91", "lon": "75.81", "address": {}}]),
        _nominatim([]),
    ]

    with patch("app.tools.doctor_finder.requests.post", side_effect=hang):
        started = real_time.monotonic()
        results = find_doctors("Ludhiana", "hospital")
        elapsed = real_time.monotonic() - started

    assert [r["name"] for r in results] == ["City Hospital"]
    assert elapsed < doctor_finder.OVERPASS_GRACE + 2
