import pytest

from app.report.extractor import ExtractionFailed, clean_json_response


def test_strips_markdown_fences():
    assert clean_json_response('```json\n{"a": 1, "b": 2}\n```') == {"a": 1, "b": 2}


def test_strips_bare_fences():
    assert clean_json_response('```\n{"a": 1}\n```') == {"a": 1}


def test_handles_plain_json():
    result = clean_json_response('{"report_type": "CBC", "parameters": {}}')
    assert result["report_type"] == "CBC"


def test_recovers_json_wrapped_in_prose():
    # The model frequently prefixes its answer; this used to lose the
    # whole page to a JSONDecodeError.
    raw = 'Here is the extracted data:\n{"report_type": "CBC", "parameters": {}}\nHope that helps!'
    assert clean_json_response(raw)["report_type"] == "CBC"


def test_recovers_json_containing_braces_in_strings():
    raw = 'Result: {"note": "range is {13-16}", "report_type": "CBC"}'
    assert clean_json_response(raw)["note"] == "range is {13-16}"


def test_recovers_json_containing_escaped_quotes():
    raw = 'Output {"note": "he said \\"high\\"", "report_type": "LFT"}'
    assert clean_json_response(raw)["report_type"] == "LFT"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_empty_response_raises_extraction_failed(raw):
    with pytest.raises(ExtractionFailed):
        clean_json_response(raw)


def test_unparseable_response_raises_extraction_failed():
    # Not a JSONDecodeError - the caller counts extraction failures
    # rather than losing the page to a bare except.
    with pytest.raises(ExtractionFailed):
        clean_json_response("this is not json at all")


def test_json_array_is_rejected():
    with pytest.raises(ExtractionFailed):
        clean_json_response("[1, 2, 3]")
