"""Patient-safety copy applied at the API boundary.

The only disclaimer in the system used to be a footer line inside the
generated PDF. Chat answers, triage verdicts and diet plans carried none,
and a triage result with emergency=True rendered "Emergency: True" as a
bare field before routing to a doctor lookup - it never told the patient
to call emergency services.

Applying this at the boundary rather than per-agent means a new agent
cannot forget it.
"""

from app.logging_config import get_logger

logger = get_logger(__name__)

DISCLAIMER = (
    "_This is AI-generated information, not a diagnosis, and does not replace "
    "advice from a qualified clinician._"
)

EMERGENCY_BANNER = (
    "## ⚠️ Seek emergency care now\n\n"
    "Your symptoms may indicate a medical emergency. **Do not wait for this "
    "chat.** Call your local emergency number immediately "
    "(**112** in India, **999** in the UK, **911** in the US), or go to the "
    "nearest emergency department.\n\n"
    "If you are alone, call someone to stay with you.\n\n"
    "---\n"
)

# Severity 4 and 5 on the classifier's 1-5 scale are "Serious" and
# "Emergency" respectively.
EMERGENCY_SEVERITY_THRESHOLD = 4


def is_emergency(severity: int | None, emergency_flag: bool | None) -> bool:

    if emergency_flag:
        return True

    return bool(severity) and severity >= EMERGENCY_SEVERITY_THRESHOLD


def with_disclaimer(response: str) -> str:
    """Append the disclaimer unless it is already present."""

    text = (response or "").rstrip()

    if not text:
        return text

    if "does not replace advice" in text or "not a substitute" in text.lower():
        return text

    return f"{text}\n\n{DISCLAIMER}"


def with_emergency_banner(response: str) -> str:
    """Lead with emergency instructions, before anything else."""

    return f"{EMERGENCY_BANNER}\n{response or ''}"


def apply_safety(response: str, severity: int | None = None, emergency: bool | None = None) -> str:
    """The single place every patient-facing response passes through."""

    text = response or ""

    if is_emergency(severity, emergency):
        logger.info("Emergency escalation applied", extra={"severity": severity})
        text = with_emergency_banner(text)

    return with_disclaimer(text)
