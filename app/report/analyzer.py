"""Interpret extracted lab parameters against their reference ranges.

The rule that matters here: a value we could not interpret is reported as
"Unknown", never as "Normal". The previous implementation fell back to
"Normal" on an unparseable value, an unparseable reference range, and on
any exception, so a genuinely dangerous result arriving in an unexpected
format was shown to the patient as fine - and the dashboard's "all values
within normal range" banner then confirmed it.
"""

import re

from app.logging_config import get_logger

logger = get_logger(__name__)

NORMAL = "Normal"
HIGH = "High"
LOW = "Low"
BORDERLINE = "Borderline"
UNKNOWN = "Unknown"

VALID_STATUSES = frozenset({HIGH, LOW, NORMAL, BORDERLINE})
ABNORMAL_STATUSES = frozenset({HIGH, LOW, BORDERLINE})


def _parse_numeric(raw_value):
    """First number in messy real-world lab text.

    "10,570" -> 10570.0, "<148" -> 148.0, "7.1%" -> 7.1, "168 mg/dL" -> 168.0
    Returns None when nothing numeric is present.
    """

    if raw_value is None:
        return None

    cleaned = str(raw_value).replace(",", "")

    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)

    return float(match.group(0)) if match else None


def parse_reference_range(reference_range):
    """Lower and upper bounds from a reference range string.

    Handles "13.0 - 16.5", "4,000-10,000", "<16.7" (upper only),
    ">60" (lower only), "13.0 to 16.5", "up to 200" and en/em dashes.
    Returns (None, None) when it cannot be parsed at all.
    """

    if not reference_range:
        return None, None

    text = str(reference_range).replace(",", "").strip()

    # Normalise the dash variants labs actually print.
    text = text.replace("–", "-").replace("—", "-").replace("−", "-")

    if not text:
        return None, None

    lowered = text.lower()

    if lowered.startswith(("<=", "<", "up to", "less than", "upto")):
        return None, _parse_numeric(text)

    if lowered.startswith((">=", ">", "more than", "greater than", "at least")):
        return _parse_numeric(text), None

    separator = " to " if " to " in lowered else "-" if "-" in text else None

    if separator:
        parts = text.split(separator) if separator == " to " else _split_range(text)

        if len(parts) == 2:
            lower = _parse_numeric(parts[0])
            upper = _parse_numeric(parts[1])

            if lower is not None and upper is not None:
                # Some reports print the bounds the wrong way round.
                return (lower, upper) if lower <= upper else (upper, lower)

            return lower, upper

    # A bare number is not a range, and neither is free text. Refusing to
    # guess is the point - the caller reports Unknown rather than Normal.
    return None, None


def _split_range(text: str) -> list[str]:
    """Split on the range dash, not on a leading minus sign.

    "-2.5 - 3.0" is a negative lower bound, not three fields.
    """

    match = re.match(r"^\s*(-?\d[\d.]*)\s*-\s*(-?\d[\d.]*)\s*$", text)

    return [match.group(1), match.group(2)] if match else [text]


def analyze_parameter(value, lower, upper):
    """Status for a numeric value against known bounds."""

    if value is None:
        return UNKNOWN

    if lower is None and upper is None:
        return UNKNOWN

    if lower is not None and value < lower:
        return LOW

    if upper is not None and value > upper:
        return HIGH

    return NORMAL


def normalize_status(raw_status) -> str:
    """Map a status the report itself printed onto our vocabulary.

    Returns "" when the text does not clearly say one of them, so the
    caller falls through to computing it from the reference range.
    """

    if not raw_status:
        return ""

    text = str(raw_status).strip().lower()

    if "border" in text:
        return BORDERLINE

    if "high" in text or "elevat" in text or "above" in text or "↑" in text:
        return HIGH

    if "low" in text or "deficien" in text or "below" in text or "↓" in text:
        return LOW

    if any(word in text for word in ("normal", "acceptable", "desirable", "within", "optimal")):
        return NORMAL

    return ""


def analyze_report(report_data: dict) -> dict:
    """Attach a status to every parameter, and a summary of the outcome."""

    parameters = report_data.get("parameters") or {}

    counts = {HIGH: 0, LOW: 0, NORMAL: 0, BORDERLINE: 0, UNKNOWN: 0}

    for test_name, test_info in parameters.items():
        if not isinstance(test_info, dict):
            logger.warning("Skipping malformed parameter entry", extra={"parameter": test_name})
            continue

        status = _status_for(test_name, test_info)

        test_info["status"] = status
        counts[status] = counts.get(status, 0) + 1

    report_data["status_counts"] = counts
    report_data["unresolved_count"] = counts[UNKNOWN]

    if counts[UNKNOWN]:
        logger.info(
            "Report contains parameters that could not be interpreted",
            extra={"unknown_count": counts[UNKNOWN], "total": len(parameters)},
        )

    return report_data


def _status_for(test_name: str, test_info: dict) -> str:

    # 1. The source document's own status column is the most reliable
    #    signal - it beats any numeric range we could guess.
    stated = normalize_status(test_info.get("status", ""))

    if stated in VALID_STATUSES:
        return stated

    # 2. Otherwise compute it from the value and the reference range.
    try:
        value = _parse_numeric(test_info.get("value"))
        lower, upper = parse_reference_range(test_info.get("reference_range", ""))

        status = analyze_parameter(value, lower, upper)

    except Exception:
        logger.exception("Could not interpret parameter", extra={"parameter": test_name})
        return UNKNOWN

    if status == UNKNOWN:
        logger.debug("Parameter left unresolved", extra={"parameter": test_name})

    return status
