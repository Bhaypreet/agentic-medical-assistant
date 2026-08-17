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
