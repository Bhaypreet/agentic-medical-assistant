import uuid
from unittest.mock import patch

import pytest

from app.agents import report_agent as module
from app.report.extractor import ExtractionFailed

PAGE_TEXT = """
Complete Blood Count
Hemoglobin   9.0 g/dL   13.0 - 16.5
"""

EXTRACTED = {
    "report_type": "CBC",
    "parameters": {
        "Hemoglobin": {
            "value": "9.0",
            "unit": "g/dL",
            "reference_range": "13.0 - 16.5",
            "status": "",
        }
    },
}


@pytest.fixture
def session_id():
    return str(uuid.uuid4())


def test_successful_report_is_analyzed_and_summarised(session_id):

    with (
        patch.object(module, "extract_report_pages", return_value=[{"page": 1, "text": PAGE_TEXT}]),
        patch.object(module, "ingest_report", return_value=str(uuid.uuid4())),
        patch.object(module, "extract_structured_report", return_value=dict(EXTRACTED)),
        patch.object(module, "generate_summary", return_value="Haemoglobin is low.") as summary,
    ):
        result = module.report_agent("report.pdf", session_id)

    assert result["summary"] == "Haemoglobin is low."
    assert result["analysis"][0]["parameters"]["Hemoglobin"]["status"] == "Low"
    assert result["outcome"]["pages_analyzed"] == 1
    assert summary.call_count == 1


def test_no_extractable_values_never_asks_for_a_summary(session_id):
    # The whole point: an empty analysis used to still produce a
    # confident "Overall Summary / Abnormal Findings / Recommendations"
    # about a report the model had never seen.
    with (
        patch.object(
            module, "extract_report_pages", return_value=[{"page": 1, "text": "Invoice 1200"}]
        ),
        patch.object(module, "ingest_report", return_value=str(uuid.uuid4())),
        patch.object(module, "generate_summary") as summary,
    ):
        result = module.report_agent("report.pdf", session_id)

    summary.assert_not_called()
    assert result["analysis"] == []
    assert "Could not read this report" in result["summary"]
    assert result["outcome"]["pages_skipped"] == 1


def test_failed_pages_are_counted_and_surfaced(session_id):

    pages = [{"page": 1, "text": PAGE_TEXT}, {"page": 2, "text": PAGE_TEXT}]

    with (
        patch.object(module, "extract_report_pages", return_value=pages),
        patch.object(module, "ingest_report", return_value=str(uuid.uuid4())),
        patch.object(
            module,
            "extract_structured_report",
            side_effect=[dict(EXTRACTED), ExtractionFailed("bad json")],
        ),
        patch.object(module, "generate_summary", return_value="Summary."),
    ):
        result = module.report_agent("report.pdf", session_id)

    assert result["outcome"]["pages_analyzed"] == 1
    assert result["outcome"]["pages_failed"] == 1
    assert any("could not be read" in w for w in result["outcome"]["warnings"])


def test_unresolved_values_are_surfaced_as_a_warning(session_id):

    unreadable = {
        "report_type": "CBC",
        "parameters": {"Culture": {"value": "No growth", "reference_range": "", "status": ""}},
    }

    with (
        patch.object(module, "extract_report_pages", return_value=[{"page": 1, "text": PAGE_TEXT}]),
        patch.object(module, "ingest_report", return_value=str(uuid.uuid4())),
        patch.object(module, "extract_structured_report", return_value=unreadable),
        patch.object(module, "generate_summary", return_value="Summary."),
    ):
        result = module.report_agent("report.pdf", session_id)

    assert result["outcome"]["unresolved_values"] == 1
    assert any("Unknown" in w for w in result["outcome"]["warnings"])


def test_summary_agent_refuses_an_empty_analysis():
    from app.agents.summary_agent import generate_summary

    with pytest.raises(ValueError):
        generate_summary([])
