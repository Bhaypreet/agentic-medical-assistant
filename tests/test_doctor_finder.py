from unittest.mock import MagicMock, patch

import pytest

from app.tools.doctor_finder import LookupFailed, find_doctors


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
def test_all_mirrors_failing_raises_rather_than_reporting_no_results(mock_get, _post, _sleep):

    mock_get.return_value = _geocode()

    # "we could not check" must be distinguishable from "nothing nearby",
    # so the caller can say so instead of telling a patient there are no
    # hospitals near them.
    with pytest.raises(LookupFailed):
        find_doctors("Ludhiana", "hospital")
