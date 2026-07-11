from unittest.mock import patch, MagicMock

from app.tools.severity_classifier import classify_severity


@patch("app.tools.severity_classifier.safe_invoke")
def test_classify_severity_parses_valid_json(mock_invoke):

    mock_response = MagicMock()
    mock_response.content = """
    {
        "severity": 5,
        "risk_level": "Emergency",
        "emergency": true,
        "specialist": "Cardiologist",
        "possible_conditions": ["Heart Attack"],
        "reasoning": "Severe chest pain is a red flag."
    }
    """
    mock_invoke.return_value = mock_response

    result = classify_severity("severe chest pain")

    assert result["severity"] == 5
    assert result["specialist"] == "Cardiologist"
    assert result["emergency"] is True