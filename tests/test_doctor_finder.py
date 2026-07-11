from unittest.mock import patch, MagicMock

from app.tools.doctor_finder import find_doctors


@patch("app.tools.doctor_finder.requests.post")
@patch("app.tools.doctor_finder.requests.get")
def test_find_doctors_returns_parsed_results(mock_get, mock_post):

    mock_geocode_response = MagicMock()
    mock_geocode_response.json.return_value = [{"lat": "30.9", "lon": "75.8"}]
    mock_geocode_response.raise_for_status.return_value = None
    mock_get.return_value = mock_geocode_response

    mock_overpass_response = MagicMock()
    mock_overpass_response.json.return_value = {
        "elements": [
            {
                "tags": {"name": "Test Hospital", "addr:city": "Ludhiana"},
                "lat": 30.9,
                "lon": 75.8
            }
        ]
    }
    mock_overpass_response.raise_for_status.return_value = None
    mock_post.return_value = mock_overpass_response

    results = find_doctors("Ludhiana", "hospital")

    assert len(results) == 1
    assert results[0]["name"] == "Test Hospital"
    assert results[0]["location"]["lat"] == 30.9


@patch("app.tools.doctor_finder.requests.get")
def test_find_doctors_returns_empty_when_location_not_found(mock_get):

    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    results = find_doctors("asdkfjaslkdjf", "hospital")

    assert results == []


def test_find_doctors_returns_empty_for_blank_location():

    assert find_doctors("", "hospital") == []
    assert find_doctors("   ", "hospital") == []