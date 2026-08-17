"""Route an incoming message to the agent that should handle it.

Two ordering bugs used to send patients describing real symptoms away
from triage:

  * greetings were checked before symptoms, so "hey, I've had crushing
    chest pain since morning" classified as a greeting - and the greeting
    branch also cleared any pending triage state.
  * informational phrasing was checked before symptoms, so "explain my
    chest pain" went to the general knowledge chain and never reached the
    severity classifier.

Symptoms are now detected first, and the informational and greeting paths
only win when the message contains nothing else. A message whose language
we do not have keywords for falls back to the model rather than silently
defaulting to "general".
"""

import re
import unicodedata

from app.logging_config import get_logger
from app.session.session_manager import ANONYMOUS, session_manager

logger = get_logger(__name__)

# --------------------------------------------------------------------
# Vocabulary
#
# Hindi, Hinglish and Punjabi terms are included because every prompt in
# this service instructs the model to answer in the patient's language and
# the UI advertises that. Matching English only meant a symptom described
# in any of those fell through to the general chain and was never triaged.
# --------------------------------------------------------------------

SYMPTOM_WORDS = [
    # English
    "pain", "paining", "hurt", "hurts", "hurting", "ache", "aching", "sore",
    "fever", "headache", "migraine", "vomiting", "nausea", "cold", "cough",
    "weakness", "dizzy", "dizziness", "fainting", "infection", "swelling",
    "rash", "bleeding", "breathless", "breathing", "chills", "cramps",
    "diarrhea", "diarrhoea", "constipation", "burning", "numbness",
    # Hinglish / romanised Hindi and Punjabi
    "dard", "bukhar", "sardi", "khansi", "ulti", "chakkar", "kamzori",
    "sir dard", "pet dard", "saans", "jalan", "sujan", "thakan",
    # Devanagari
    "दर्द", "बुखार", "खांसी", "उल्टी", "चक्कर", "कमजोरी", "सर्दी", "साँस",
    # Gurmukhi
    "ਦਰਦ", "ਬੁਖਾਰ", "ਖੰਘ", "ਉਲਟੀ", "ਚੱਕਰ", "ਕਮਜ਼ੋਰੀ",
]

# Markers that make a message about the speaker's own body rather than a
# general question. "what is chest pain" is a question; "explain my chest
# pain" is a patient describing a symptom.
# "me" is deliberately absent - "tell me about diabetes" is a general
# question, not a patient describing their own body.
PERSONAL_MARKERS = [
    "my", "mine", "i have", "i've", "ive", "i am", "i'm", "i feel", "i felt",
    "i get", "having", "mera", "meri", "mujhe", "mainu",
    "मुझे", "मेरा", "मेरी", "ਮੈਨੂੰ", "ਮੇਰਾ",
]

GREETING_WORDS = [
    "hi", "hello", "hey", "hiya", "yo", "good morning", "good afternoon",
    "good evening", "namaste", "namaskar", "salaam", "sat sri akal",
    "नमस्ते", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ",
]

INFORMATIONAL_STARTERS = [
    "what is", "what are", "why does", "why do", "why is", "explain",
    "define", "tell me about", "how does", "how do", "difference between",
    "causes of", "symptoms of", "types of", "what causes", "how to prevent",
    "how to avoid", "kya hai", "kya hota", "क्या है", "ਕੀ ਹੈ",
]

CANCEL_WORDS = [
    "cancel", "never mind", "nevermind", "stop", "forget it", "leave it",
    "rehne do", "chhodo",
]

DIET_WORDS = [
    "diet", "meal plan", "nutrition", "food plan", "what should i eat",
    "diet plan", "meal", "eating plan", "calories", "khana", "khaana",
    "आहार", "खाना", "ਖੁਰਾਕ",
]

LOOKUP_WORDS = [
    "hospital", "hospitals", "doctor", "doctors", "clinic", "clinics",
    "cardiologist", "specialist", "dermatologist", "dentist", "neurologist",
    "orthopedic", "gynecologist", "pediatrician", "physician",
    "अस्पताल", "डॉक्टर", "ਹਸਪਤਾਲ", "ਡਾਕਟਰ",
]

REPORT_WORDS = [
    "report", "result", "results", "blood test", "lab", "hemoglobin",
    "haemoglobin", "cholesterol", "sugar", "thyroid", "wbc", "rbc",
    "रिपोर्ट", "ਰਿਪੋਰਟ",
]


def _is_latin(text: str) -> bool:
    """True when the message is written in a Latin script."""

    letters = [ch for ch in text if ch.isalpha()]

    if not letters:
        return True

    latin = sum(1 for ch in letters if "LATIN" in unicodedata.name(ch, ""))

    return latin / len(letters) > 0.5


def _contains(text: str, words: list[str]) -> bool:
    """Whole-word match for Latin script, substring match otherwise.

    Word boundaries are a Latin-script concept; \\b does not delimit
    Devanagari or Gurmukhi, so those terms are matched as substrings.
    """

    for word in words:

        if _is_latin(word):
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
                return True
        elif word in text:
            return True

    return False


def _is_only_greeting(text: str) -> bool:
    """True when the message is a greeting and nothing else.

    Previously any message merely containing "hi" or "hey" was treated as
    a greeting, which discarded the rest of the sentence.
    """

    stripped = re.sub(r"[^\w\s]", " ", text).strip()

    for word in sorted(GREETING_WORDS, key=len, reverse=True):
        if stripped == word or stripped.startswith(f"{word} "):
            remainder = stripped[len(word):].strip()
            if not remainder or remainder in {"there", "doctor", "doc", "assistant"}:
                return True

    return False


def _llm_fallback(query: str) -> str | None:
    """Ask the model to classify a message our keywords do not cover.

    Only used for non-Latin-script messages that matched nothing, so the
    cost is bounded to the case that previously failed outright.
    """

    from app.llm.model import safe_invoke
    from app.supervisor.prompt import SUPERVISOR_PROMPT

    valid = {"symptom", "report_chat", "general", "greeting", "diet", "hospital_search"}

    try:
        answer = safe_invoke(SUPERVISOR_PROMPT.format(query=query)).content
    except Exception:
        logger.exception("Supervisor fallback classification failed")
        return None

    label = (answer or "").strip().lower().split()[:1]

    if label and label[0] in valid:
        logger.info("Classified by model fallback", extra={"intent": label[0]})
        return label[0]

    return None


def classify_intent(
    query: str,
    session_id: str,
    pdf_path: str = "",
    owner: str = ANONYMOUS,
) -> str:

    if pdf_path:
        return "report_upload"

    text = (query or "").lower().strip()

    if not text:
        return "general"

    def _clear_pending() -> None:
        session_manager.clear_pending_specialist(session_id, owner=owner)
        session_manager.clear_pending_clarification(session_id, owner=owner)

    has_symptom = _contains(text, SYMPTOM_WORDS)
    is_personal = _contains(text, PERSONAL_MARKERS)
    is_informational = any(
        text.startswith(phrase) or f" {phrase}" in text for phrase in INFORMATIONAL_STARTERS
    )

    # 1. A symptom the patient is reporting about themselves outranks
    #    everything, including a greeting in the same sentence and a
    #    pending clarification or location wait.
    if has_symptom and (is_personal or not is_informational):
        _clear_pending()
        return "symptom"

    has_report = session_manager.get_report(session_id, owner=owner) is not None

    # 2. A question about the patient's own uploaded report. This is
    #    checked before the informational path so that "why is my
    #    hemoglobin low" reaches the report, not the encyclopaedia.
    if has_report and is_personal and _contains(text, REPORT_WORDS):
        return "report_chat"

    # 3. A general question about a condition - no first-person framing.
    if is_informational:
        return "general"

    # 4. An explicit cancellation drops any pending flow.
    if _contains(text, CANCEL_WORDS):
        _clear_pending()
        return "general"

    # 5. A greeting, only when the message is nothing but a greeting.
    if _is_only_greeting(text):
        _clear_pending()
        return "greeting"

    # 6. Resume whatever the assistant last asked for.
    if session_manager.get_pending_clarification(session_id, owner=owner):
        return "clarify_answer"

    if session_manager.get_pending_specialist(session_id, owner=owner):
        return "provide_location"

    if _contains(text, DIET_WORDS):
        return "diet"

    if _contains(text, LOOKUP_WORDS):
        return "hospital_search"

    if has_report and (_contains(text, REPORT_WORDS) or is_personal):
        return "report_chat"

    # 7. Nothing matched. If the message is not in a script our keywords
    #    cover, ask the model rather than defaulting to "general".
    if not _is_latin(text):
        fallback = _llm_fallback(query)

        if fallback == "symptom":
            _clear_pending()

        if fallback:
            return fallback

    return "report_chat" if has_report else "general"
