"""Turn a described symptom into a structured triage result.

This is on the safety path, and it used to be a single model call parsed
once with no recovery: any preamble or truncation raised and failed the
whole request. It now recovers embedded JSON, asks the model to repair
malformed output once, validates the result against the schema, and falls
back to a conservative "see a clinician" verdict rather than surfacing an
error to someone describing a symptom.
"""

from pydantic import ValidationError

from app.llm.model import safe_invoke
from app.logging_config import get_logger
from app.models.severity_model import SeverityOutput
from app.prompts.severity_prompt import SEVERITY_PROMPT
from app.report.extractor import ExtractionFailed, clean_json_response

logger = get_logger(__name__)

REPAIR_PROMPT = """The following was supposed to be valid JSON matching this shape:

{{"severity": 1-5, "risk_level": "...", "emergency": true/false,
  "specialist": "...", "possible_conditions": ["..."], "reasoning": "..."}}

Return the same assessment as valid JSON only - no markdown, no commentary.

{broken}
"""

# Used when the model cannot be parsed at all. Deliberately cautious: it
# routes the patient to a clinician rather than reassuring them.
FALLBACK = {
    "severity": 3,
    "risk_level": "Uncertain",
    "emergency": False,
    "specialist": "General Physician",
    "possible_conditions": [],
    "reasoning": (
        "This symptom could not be assessed automatically. Please describe it to a "
        "clinician, and seek urgent care if it worsens quickly or you feel unsafe."
    ),
}


def _parse(raw: str) -> dict:

    parsed = clean_json_response(raw)

    validated = SeverityOutput.model_validate(parsed)

    return validated.model_dump()


def classify_severity(query: str) -> dict:

    raw = safe_invoke(SEVERITY_PROMPT.format(query=query)).content or ""

    try:
        return _parse(raw)
    except (ExtractionFailed, ValidationError):
        logger.warning("Triage response was not usable; requesting a repair")

    try:
        repaired = safe_invoke(REPAIR_PROMPT.format(broken=raw[:4000])).content or ""
        return _parse(repaired)
    except Exception:
        logger.exception("Triage classification failed; using the cautious fallback")

    return dict(FALLBACK)
