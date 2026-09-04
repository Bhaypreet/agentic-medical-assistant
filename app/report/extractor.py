"""Turn a page of report text into structured parameters.

Two things changed here. The raw model response - every parsed lab value
for a named patient - was printed to stdout on every page; that is now
behind the debug flag the config forbids in production. And JSON parsing
was a single json.loads() with no recovery, so any preamble, trailing
note or truncation lost the whole page with only a printed message.
"""

import json
import re

from app.config import settings
from app.llm.model import safe_invoke
from app.logging_config import get_logger

logger = get_logger(__name__)

EXTRACTION_PROMPT = """
You are an expert medical report extraction system.

Extract every laboratory parameter from the report below.

Return ONLY valid JSON, with no markdown formatting and no commentary, in
exactly this shape:

{{
    "report_type": "...",
    "parameters": {{
        "Hemoglobin": {{
            "value": "...",
            "unit": "...",
            "reference_range": "...",
            "status": "..."
        }}
    }}
}}

Rules for "status":
- If the report text explicitly states a status/flag/comment for this value
  (e.g. "High", "Low", "Normal", "Borderline", "Deficient", "Elevated",
  arrows like up/down, or a Status/Comment column), use that EXACT wording,
  normalized to one of: "High", "Low", "Normal", "Borderline".
- Only if no status is stated anywhere in the source text, leave it as an
  empty string "" - it will be calculated later from the reference range.
- Never guess a status - only report what the text actually says.

If the page contains no laboratory parameters at all, return:
{{"report_type": "Unknown", "parameters": {{}}}}

Medical Report:

{report}
"""

REPAIR_PROMPT = """The following was supposed to be valid JSON but could not be parsed.

Return the same data as valid JSON only - no markdown fences, no commentary,
no explanation. Do not invent values that are not present.

{broken}
"""


class ExtractionFailed(RuntimeError):
    """The page could not be turned into structured data."""


def extract_report_information(report_text: str) -> str:
    """Raw model output for one page of report text."""

    response = safe_invoke(EXTRACTION_PROMPT.format(report=report_text))

    content = response.content or ""

    logger.info("Received extraction response", extra={"characters": len(content)})

    if settings.debug_log_report_content:
        logger.debug("Raw extraction response (debug only)", extra={"response": content[:1000]})

    return content


def _strip_fences(text: str) -> str:

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    return text.strip()


def _first_json_object(text: str) -> str | None:
    """Longest balanced {...} span in the text.

    Recovers the payload when the model wraps it in a sentence such as
    "Here is the extracted data: {...}".
    """

    start = text.find("{")

    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    return None


def clean_json_response(response_text: str) -> dict:
    """Parse a model response into a dict, recovering where possible.

    Raises ExtractionFailed rather than letting a JSONDecodeError escape,
    so the caller can count the failure instead of losing the page to a
    bare except.
    """

    if not response_text or not response_text.strip():
        raise ExtractionFailed("The model returned an empty extraction response.")

    candidates = [_strip_fences(response_text)]

    embedded = _first_json_object(candidates[0])

    if embedded and embedded != candidates[0]:
        candidates.append(embedded)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    raise ExtractionFailed("The model response was not valid JSON.")


def extract_structured_report(report_text: str) -> dict:
    """Extract one page, asking the model to repair its own bad JSON once."""

    raw = extract_report_information(report_text)

    try:
        return clean_json_response(raw)
    except ExtractionFailed:
        logger.warning("Extraction response was not parseable; requesting a repair")

    repaired = safe_invoke(REPAIR_PROMPT.format(broken=raw[:6000])).content

    return clean_json_response(repaired or "")
