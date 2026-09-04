from app.tools.pdf_report_generator import _sanitize, generate_report_pdf

ANALYSIS = [
    {
        "report_type": "CBC",
        "parameters": {
            "Hemoglobin": {"value": "9.0", "unit": "g/dL", "status": "Low"},
            "Culture": {"value": "No growth", "unit": "", "status": "Unknown"},
        },
    }
]


def _pdf(summary="Overall Summary:\n- Haemoglobin is low.", analysis=ANALYSIS):
    return generate_report_pdf(summary_text=summary, analysis=analysis)


def test_generates_a_pdf():
    output = _pdf()
    assert output.startswith(b"%PDF")


def test_handles_an_empty_analysis():
    assert _pdf(summary="Nothing to report.", analysis=[]).startswith(b"%PDF")


def test_handles_a_missing_summary():
    assert generate_report_pdf(summary_text="", analysis=ANALYSIS).startswith(b"%PDF")


def test_raw_html_in_model_output_does_not_crash_the_build():
    # ReportLab's Paragraph parser treats these as real tags.
    summary = "Findings:\n- Value <br> is high\n- Unclosed <b tag here\n- 5 < 10 and 20 > 3"
    assert _pdf(summary=summary).startswith(b"%PDF")


def test_markdown_tables_do_not_crash_the_build():
    summary = "| Test | Result |\n| --- | --- |\n| Hb | 9.0 |"
    assert _pdf(summary=summary).startswith(b"%PDF")


def test_emoji_are_stripped_rather_than_breaking_the_font():
    assert _sanitize("Result 🔴 high ⚠️") == "Result  high"


def test_malformed_parameter_entries_are_skipped():
    analysis = [{"report_type": "CBC", "parameters": {"Broken": "not a dict"}}]
    assert _pdf(analysis=analysis).startswith(b"%PDF")


def test_html_special_characters_are_escaped():
    assert _sanitize("a < b & c > d") == "a &lt; b &amp; c &gt; d"
