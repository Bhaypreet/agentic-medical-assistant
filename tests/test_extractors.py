import json
import pytest

from app.report.extractor import clean_json_response


def test_clean_json_response_strips_markdown_fences():

    raw = '```json\n{"a": 1, "b": 2}\n```'
    result = clean_json_response(raw)

    assert result == {"a": 1, "b": 2}


def test_clean_json_response_handles_plain_json():

    raw = '{"report_type": "CBC", "parameters": {}}'
    result = clean_json_response(raw)

    assert result["report_type"] == "CBC"


def test_clean_json_response_raises_on_invalid_json():

    with pytest.raises(json.JSONDecodeError):
        clean_json_response("this is not json at all")
        