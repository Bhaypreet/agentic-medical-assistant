import re


def _parse_numeric(raw_value: str):
    """
    Extracts the first number from messy real-world lab text:
    "10,570" -> 10570.0
    "<148"   -> 148.0
    "7.1%"   -> 7.1
    "168 mg/dL" -> 168.0
    Returns None if nothing numeric could be found.
    """

    if raw_value is None:
        return None

    cleaned = str(raw_value).replace(",", "")

    match = re.search(r"-?\d+(\.\d+)?", cleaned)

    if not match:
        return None

    return float(match.group(0))


def parse_reference_range(reference_range: str):
    """
    Handles multiple real-world reference range formats:
    "13.0 - 16.5"   -> (13.0, 16.5)
    "4,000-10,000"  -> (4000.0, 10000.0)
    "<16.7"         -> (None, 16.7)   (upper bound only)
    ">60"           -> (60.0, None)   (lower bound only)
    Returns (None, None) if it can't be parsed at all.
    """

    if not reference_range:
        return None, None

    text = str(reference_range).replace(",", "").strip()

    if text.startswith("<"):
        value = _parse_numeric(text)
        return None, value

    if text.startswith(">"):
        value = _parse_numeric(text)
        return value, None

    if "-" in text:
        parts = text.split("-")
        if len(parts) == 2:
            lower = _parse_numeric(parts[0])
            upper = _parse_numeric(parts[1])
            return lower, upper

    return None, None


def analyze_parameter(value: float, lower, upper):

    if lower is not None and value < lower:
        return "Low"

    if upper is not None and value > upper:
        return "High"

    return "Normal"


_VALID_STATUSES = {"High", "Low", "Normal", "Borderline"}


def _normalize_status(raw_status: str):

    if not raw_status:
        return ""

    text = str(raw_status).strip().lower()

    if "border" in text:
        return "Borderline"
    if "high" in text or "elevat" in text or "↑" in text:
        return "High"
    if "low" in text or "deficien" in text or "↓" in text:
        return "Low"
    if "normal" in text or "acceptable" in text or "desirable" in text or "within" in text:
        return "Normal"

    return ""


def analyze_report(report_data: dict):

    parameters = report_data.get("parameters", {})

    for test_name, test_info in parameters.items():

        # 1. Prefer a status the report itself already stated (most reliable -
        #    the source document's own Status/Comment column beats any
        #    numeric range guess we could make).
        extracted_status = _normalize_status(test_info.get("status", ""))

        if extracted_status in _VALID_STATUSES:
            test_info["status"] = extracted_status
            continue

        # 2. Otherwise, fall back to calculating it from value + reference range.
        try:
            value = _parse_numeric(test_info.get("value"))
            lower, upper = parse_reference_range(test_info.get("reference_range", ""))

            if value is None or (lower is None and upper is None):
                test_info["status"] = "Normal"
                continue

            test_info["status"] = analyze_parameter(value, lower, upper)

        except Exception:
            test_info["status"] = "Normal"

    return report_data