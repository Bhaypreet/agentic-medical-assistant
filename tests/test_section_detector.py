from app.report.section_detector import detect_report_type


def test_detects_known_report_type():

    sample = """
    Complete Blood Count

    Hemoglobin
    Platelet Count
    """

    assert detect_report_type(sample) == "CBC"


def test_detection_is_case_insensitive():

    assert detect_report_type("lipid profile results") == "Lipid Profile"


def test_returns_none_for_unrecognised_page():

    assert detect_report_type("Invoice for laboratory services") is None


def test_detects_broadened_keywords():
    assert detect_report_type("Renal Function Panel") == "KFT"
    assert detect_report_type("Serum Ferritin") == "Iron Studies"
    assert detect_report_type("TSH, Free T3, Free T4") == "Thyroid Function Test"


def test_accepts_a_results_table_without_a_known_heading():
    # A page whose heading is worded unusually used to be dropped from
    # the analysis entirely.
    page = """
    Sodium        139 mmol/L    135 - 145
    Potassium     4.2 mmol/L    3.5 - 5.1
    Chloride      101 mmol/L    98 - 107
    """
    assert detect_report_type(page) == "Laboratory Report"


def test_accepts_a_page_with_generic_table_headings():
    page = "Test Name    Result    Units    Biological Reference Interval"
    assert detect_report_type(page) == "Laboratory Report"


def test_rejects_a_page_with_no_results():
    assert detect_report_type("Invoice for laboratory services. Amount due: 1200") is None
    assert detect_report_type("") is None
    assert detect_report_type("   ") is None
