KNOWN_REPORT_TYPES = {
    "Complete Blood Count": "CBC",
    "CBC": "CBC",
    "Lipid Profile": "Lipid Profile",
    "Thyroid": "Thyroid Function Test",
    "HbA1c": "HbA1c",
    "Glycosylated Hemoglobin": "HbA1c",
    "Blood Sugar": "Blood Sugar",
    "Vitamin D": "Vitamin D",
    "Iron Studies": "Iron Studies",
    "Liver Function Test": "LFT",
    "Kidney Function Test": "KFT",
    "Urine": "Urine Test"
}

def detect_report_type(page_text: str):
    """
    Detect the report type present in a page.
    Returns the report name if found, otherwise None.
    """

    page_text = page_text.lower()

    for keyword, report_type in KNOWN_REPORT_TYPES.items():

        if keyword.lower() in page_text:
            return report_type

    return None