from unittest.mock import MagicMock, patch

from app.tools.severity_classifier import FALLBACK, classify_severity


def _response(content):
    mock = MagicMock()
    mock.content = content
    return mock


@patch("app.tools.severity_classifier.safe_invoke")
def test_parses_a_valid_response(mock_invoke):

    mock_invoke.return_value = _response(
        """
        {
            "severity": 5,
            "risk_level": "Emergency",
            "emergency": true,
            "specialist": "Cardiologist",
            "possible_conditions": ["Heart Attack"],
            "reasoning": "Severe chest pain is a red flag."
        }
        """
    )

    result = classify_severity("severe chest pain")

    assert result["severity"] == 5
    assert result["specialist"] == "Cardiologist"
    assert result["emergency"] is True


@patch("app.tools.severity_classifier.safe_invoke")
def test_recovers_json_wrapped_in_prose_without_a_second_call(mock_invoke):

    mock_invoke.return_value = _response(
        'Assessment: {"severity": 2, "risk_level": "Mild", "emergency": false, '
        '"specialist": "General Physician", "possible_conditions": ["Cold"], '
        '"reasoning": "Mild."} Hope this helps.'
    )

    result = classify_severity("runny nose")

    assert result["severity"] == 2
    assert mock_invoke.call_count == 1


@patch("app.tools.severity_classifier.safe_invoke")
def test_repairs_malformed_json_on_a_second_call(mock_invoke):

    mock_invoke.side_effect = [
        _response("I think this is moderate, maybe a 3?"),
        _response(
            '{"severity": 3, "risk_level": "Moderate", "emergency": false, '
            '"specialist": "General Physician", "possible_conditions": [], '
            '"reasoning": "Moderate."}'
        ),
    ]

    result = classify_severity("persistent cough")

    assert result["severity"] == 3
    assert mock_invoke.call_count == 2


@patch("app.tools.severity_classifier.safe_invoke")
def test_unparseable_output_falls_back_cautiously(mock_invoke):

    mock_invoke.return_value = _response("no idea, sorry")

    result = classify_severity("something odd")

    # A patient describing a symptom must not receive an error, and must
    # not be reassured either.
    assert result == FALLBACK
    assert result["risk_level"] == "Uncertain"
    assert result["emergency"] is False


@patch("app.tools.severity_classifier.safe_invoke")
def test_out_of_range_severity_is_rejected_then_repaired(mock_invoke):

    mock_invoke.side_effect = [
        _response(
            '{"severity": 9, "risk_level": "Emergency", "emergency": true, '
            '"specialist": "Cardiologist", "possible_conditions": [], "reasoning": "x"}'
        ),
        _response(
            '{"severity": 5, "risk_level": "Emergency", "emergency": true, '
            '"specialist": "Cardiologist", "possible_conditions": [], "reasoning": "x"}'
        ),
    ]

    assert classify_severity("chest pain")["severity"] == 5


@patch("app.tools.severity_classifier.safe_invoke")
def test_conditions_returned_as_a_string_are_coerced_to_a_list(mock_invoke):

    mock_invoke.return_value = _response(
        '{"severity": 2, "risk_level": "Mild", "emergency": false, '
        '"specialist": "General Physician", '
        '"possible_conditions": "Cold, Flu", "reasoning": "Mild."}'
    )

    assert classify_severity("sniffles")["possible_conditions"] == ["Cold", "Flu"]
