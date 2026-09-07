"""Patient-safety copy applied at the API boundary.

The only disclaimer in the system used to be a footer line inside the
generated PDF. Chat answers, triage verdicts and diet plans carried none,
and a triage result with emergency=True rendered "Emergency: True" as a
bare field before routing to a doctor lookup - it never told the patient
to call emergency services.

Applying this at the boundary rather than per-agent means a new agent
cannot forget it.
"""

import re

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


# Presentations where spending a conversational turn on "how long has this
# been going on?" is itself the harm. These are deliberately phrase-level
# rather than single words: "chest pain" must escalate, "chest congestion"
# and "my chest feels tight after the gym" must not blanket-trigger, and a
# lone "bleeding" is a paper cut as often as a haemorrhage.
_RED_FLAG_PATTERNS = (
    r"chest (pain|pressure|tightness|discomfort)",
    r"(crushing|squeezing|radiating).{0,30}(chest|arm|jaw)",
    r"(pain|numbness).{0,20}(left arm|jaw)",
    r"(can'?t|cannot|unable to|difficulty|trouble|struggling to) breathe?",
    r"(short(ness)? of breath|gasping|choking|suffocating)",
    r"(face|arm|leg).{0,20}(drooping|weakness|numb)",
    r"(slurred speech|can'?t speak|sudden confusion)",
    r"(worst|thunderclap) headache",
    r"(unconscious|unresponsive|passed out|fainted|collapsed)",
    r"(seizure|convulsion|fitting)",
    r"(coughing|vomiting).{0,15}blood",
    r"(heavy|severe|uncontrolled|won'?t stop) bleeding",
    r"(overdose|poison|swallowed).{0,20}(pills|bleach|chemical)",
    r"(suicidal|kill myself|end my life|want to die)",
    r"anaphyla",
    # "throat is closing", "tongue is swelling" - the copula and any
    # possessive sit between the noun and the verb in real phrasing.
    r"(throat|airway).{0,15}clos",
    r"(tongue|lip|face).{0,15}swell",
    r"stiff neck.{0,30}(fever|rash)",
    # Cyanosis gets described in either order: "blue lips", "lips are
    # turning blue".
    r"blue (lips|face|fingers)",
    r"(lips|face|skin|fingers).{0,20}(turning |going |gone )?blue",
)

_RED_FLAGS = tuple(re.compile(p, re.IGNORECASE) for p in _RED_FLAG_PATTERNS)


def looks_like_emergency(text: str) -> bool:
    """Whether a symptom description carries a red flag on its face.

    Triage asks one clarifying question before assessing severity, which
    is right for a sore throat and wrong for crushing chest pain radiating
    to the arm - the patient was answering "how long has the pain been
    going on?" instead of being told to call an ambulance. This is a cheap
    pre-check, not a diagnosis: it decides whether to skip the question,
    and the classifier still sets the actual severity.
    """

    if not text:
        return False

    return any(pattern.search(text) for pattern in _RED_FLAGS)


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


_BREAK_TAG = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)


def normalise_line_breaks(response: str) -> str:
    """Turn HTML line breaks the model emits into something markdown renders.

    Models reach for `<br>` inside markdown table cells, because a table
    row cannot contain a real newline. The chat surface renders markdown
    without raw HTML - correctly, since the text is model output and
    enabling HTML would make it an injection sink - so the tags reached
    the patient as literal "<br>" in the middle of sentences.

    Inside a table row the break becomes a space, which is the only thing
    a cell can hold; everywhere else it becomes the newline it stood for.
    """

    if not response or "<" not in response:
        return response or ""

    lines = []

    for line in response.splitlines():
        if _BREAK_TAG.search(line):
            replacement = " " if line.lstrip().startswith("|") else "\n"
            line = _BREAK_TAG.sub(replacement, line)

        lines.append(line)

    # Collapse the runs of spaces a substitution can leave behind, without
    # touching indentation that markdown depends on.
    return "\n".join(
        re.sub(r"[ \t]{2,}", " ", ln) if ln.lstrip().startswith("|") else ln for ln in lines
    )


def apply_safety(response: str, severity: int | None = None, emergency: bool | None = None) -> str:
    """The single place every patient-facing response passes through."""

    text = normalise_line_breaks(response or "")

    if is_emergency(severity, emergency):
        logger.info("Emergency escalation applied", extra={"severity": severity})
        text = with_emergency_banner(text)

    return with_disclaimer(text)
