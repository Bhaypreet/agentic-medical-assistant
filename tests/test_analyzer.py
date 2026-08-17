import pytest

from app.report.analyzer import (
    HIGH,
    LOW,
    NORMAL,
    UNKNOWN,
    analyze_parameter,
    analyze_report,
    normalize_status,
    parse_reference_range,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("13.0 - 16.5", (13.0, 16.5)),
        ("13.0-16.5", (13.0, 16.5)),
        ("4,000-10,000", (4000.0, 10000.0)),
        ("70 to 110", (70.0, 110.0)),
        ("13.0 – 16.5", (13.0, 16.5)),  # en dash
        ("13.0 — 16.5", (13.0, 16.5)),  # em dash
        ("16.5 - 13.0", (13.0, 16.5)),  # printed the wrong way round
        ("-2.5 - 3.0", (-2.5, 3.0)),  # negative lower bound
        ("<16.7", (None, 16.7)),
        ("<= 200", (None, 200.0)),
        ("up to 200", (None, 200.0)),
        (">60", (60.0, None)),
        (">= 60", (60.0, None)),
        ("at least 60", (60.0, None)),
    ],
)
def test_reference_ranges_that_should_parse(text, expected):
    assert parse_reference_range(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", None, "See comments", "Negative", "120", "refer to lab"],
)
def test_reference_ranges_that_cannot_be_parsed_return_no_bounds(text):
    assert parse_reference_range(text) == (None, None)


def test_value_inside_bounds_is_normal():
    assert analyze_parameter(14.0, 13.0, 16.5) == NORMAL


def test_value_below_lower_bound_is_low():
    assert analyze_parameter(9.0, 13.0, 16.5) == LOW


def test_value_above_upper_bound_is_high():
    assert analyze_parameter(19.0, 13.0, 16.5) == HIGH


def test_open_ended_bounds_are_respected():
    assert analyze_parameter(240.0, None, 200.0) == HIGH
    assert analyze_parameter(180.0, None, 200.0) == NORMAL
    assert analyze_parameter(40.0, 60.0, None) == LOW


def test_bounds_are_inclusive():
    assert analyze_parameter(13.0, 13.0, 16.5) == NORMAL
    assert analyze_parameter(16.5, 13.0, 16.5) == NORMAL


def test_missing_value_is_unknown_not_normal():
    # The critical case: an uninterpretable result must never be
    # presented to a patient as a healthy one.
    assert analyze_parameter(None, 13.0, 16.5) == UNKNOWN


def test_missing_bounds_are_unknown_not_normal():
    assert analyze_parameter(14.0, None, None) == UNKNOWN


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        ("High", HIGH),
        ("ELEVATED", HIGH),
        ("↑", HIGH),
        ("Low", LOW),
        ("deficient", LOW),
        ("↓", LOW),
        ("Borderline", "Borderline"),
        ("Within normal limits", NORMAL),
        ("Desirable", NORMAL),
        ("", ""),
        ("see note", ""),
    ],
)
def test_status_normalisation(stated, expected):
    assert normalize_status(stated) == expected


def test_stated_status_wins_over_computed_range():

    report = analyze_report(
        {
            "parameters": {
                "Hemoglobin": {
                    "value": "14.0",
                    "reference_range": "13.0 - 16.5",
                    "status": "Borderline",
                }
            }
        }
    )

    assert report["parameters"]["Hemoglobin"]["status"] == "Borderline"


def test_unparseable_parameter_is_reported_as_unknown():

    report = analyze_report(
        {
            "parameters": {
                "Culture": {"value": "No growth", "reference_range": "", "status": ""},
            }
        }
    )

    assert report["parameters"]["Culture"]["status"] == UNKNOWN
    assert report["unresolved_count"] == 1


def test_report_reports_status_counts():

    report = analyze_report(
        {
            "parameters": {
                "Hemoglobin": {"value": "9.0", "reference_range": "13.0 - 16.5", "status": ""},
                "Glucose": {"value": "95", "reference_range": "70 - 110", "status": ""},
                "Notes": {"value": "n/a", "reference_range": "", "status": ""},
            }
        }
    )

    assert report["status_counts"][LOW] == 1
    assert report["status_counts"][NORMAL] == 1
    assert report["status_counts"][UNKNOWN] == 1


def test_malformed_parameter_entry_is_skipped_not_fatal():

    report = analyze_report({"parameters": {"Broken": "not a dict"}})

    assert report["status_counts"][UNKNOWN] == 0


def test_report_with_no_parameters_is_handled():

    report = analyze_report({"report_type": "CBC"})

    assert report["unresolved_count"] == 0
