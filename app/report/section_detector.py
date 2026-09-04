"""Decide whether a page of a report contains laboratory results.

The previous version matched a twelve-entry keyword list and returned None
for anything else, so a page whose heading was worded differently was
silently dropped from the analysis. The list is broadened here, and a page
that merely looks like a results table - a test name next to a number and
a reference range - is now accepted even when no heading matches.
"""

import re

KNOWN_REPORT_TYPES = {
    # Haematology
    "complete blood count": "CBC",
    "cbc": "CBC",
    "haemogram": "CBC",
    "hemogram": "CBC",
    "blood picture": "CBC",
    "esr": "ESR",
    "coagulation": "Coagulation Profile",
    "prothrombin": "Coagulation Profile",
    # Metabolic
    "lipid profile": "Lipid Profile",
    "lipid panel": "Lipid Profile",
    "cholesterol": "Lipid Profile",
    "hba1c": "HbA1c",
    "glycosylated hemoglobin": "HbA1c",
    "glycated haemoglobin": "HbA1c",
    "blood sugar": "Blood Sugar",
    "blood glucose": "Blood Sugar",
    "fasting glucose": "Blood Sugar",
    "glucose tolerance": "Blood Sugar",
    # Endocrine
    "thyroid": "Thyroid Function Test",
    "tsh": "Thyroid Function Test",
    "cortisol": "Endocrine Panel",
    "testosterone": "Endocrine Panel",
    # Organ panels
    "liver function": "LFT",
    "lft": "LFT",
    "hepatic panel": "LFT",
    "kidney function": "KFT",
    "kft": "KFT",
    "renal function": "KFT",
    "rft": "KFT",
    "electrolyte": "Electrolytes",
    # Vitamins and minerals
    "vitamin d": "Vitamin D",
    "vitamin b12": "Vitamin B12",
    "iron studies": "Iron Studies",
    "ferritin": "Iron Studies",
    # Other
    "urine": "Urine Test",
    "urinalysis": "Urine Test",
    "crp": "Inflammatory Markers",
    "c-reactive protein": "Inflammatory Markers",
    "culture": "Culture",
    "serology": "Serology",
}

GENERIC_HEADINGS = [
    "test name",
    "investigation",
    "reference range",
    "biological reference",
    "normal range",
    "result",
    "units",
]

# A test name, a numeric result, then something range-shaped on the same
# line - the shape of a results table row regardless of its heading.
_RESULT_ROW = re.compile(
    r"[A-Za-z][A-Za-z()/\-. ]{2,40}\s+\d+(?:[.,]\d+)?\s*[A-Za-z%/µ^]*\s*"
    r"(?:\d+(?:[.,]\d+)?\s*[-–—]\s*\d+|[<>]\s*\d+)",
)


def looks_like_results_table(page_text: str, min_rows: int = 2) -> bool:
    """True when the page contains several results-table-shaped rows."""

    return len(_RESULT_ROW.findall(page_text)) >= min_rows


def detect_report_type(page_text: str) -> str | None:
    """The report type on this page, or None when it holds no results."""

    if not page_text or not page_text.strip():
        return None

    lowered = page_text.lower()

    for keyword, report_type in KNOWN_REPORT_TYPES.items():
        if keyword in lowered:
            return report_type

    heading_hits = sum(1 for heading in GENERIC_HEADINGS if heading in lowered)

    if heading_hits >= 2 or looks_like_results_table(page_text):
        return "Laboratory Report"

    return None
