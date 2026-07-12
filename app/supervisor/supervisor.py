import re
from app.session.session_manager import session_manager


def _contains_word(query: str, words: list) -> bool:
    return any(
        re.search(rf"\b{re.escape(word)}\b", query)
        for word in words
    )


INFORMATIONAL_STARTERS = [
    "what is", "what are", "why does", "why do", "why is",
    "explain", "define", "tell me about", "how does", "how do",
    "difference between", "causes of", "symptoms of", "types of",
    "what causes", "how to prevent", "how to avoid"
]


def _is_informational_query(query: str) -> bool:
    return any(query.startswith(phrase) or f" {phrase}" in query for phrase in INFORMATIONAL_STARTERS)


def classify_intent(
    query: str,
    session_id: str,
    pdf_path: str = ""
):

    query = query.lower().strip()

    if pdf_path:
        return "report_upload"

    greeting_words = ["hi", "hello", "hey", "good morning", "good evening"]

    if _contains_word(query, greeting_words):
        session_manager.clear_pending_specialist(session_id)
        session_manager.clear_pending_clarification(session_id)
        return "greeting"

    # An informational question is answered generally, WITHOUT disturbing
    # any pending clarification/location flow - so the user can ask a
    # side question and still resume the triage flow on their next message.
    if _is_informational_query(query):
        return "general"

    symptom_words = [
        "pain", "paining", "hurts", "hurting", "ache", "aching",
        "fever", "headache", "vomiting", "cold", "cough",
        "weakness", "infection", "chest pain", "stomach pain", "breathing"
    ]

    # A genuinely NEW symptom always takes priority - interrupts any
    # pending clarification/location-wait state instead of being
    # swallowed by it.
    if _contains_word(query, symptom_words):
        session_manager.clear_pending_specialist(session_id)
        session_manager.clear_pending_clarification(session_id)
        return "symptom"

    cancel_words = ["cancel", "never mind", "nevermind", "stop", "forget it"]

    if _contains_word(query, cancel_words):
        session_manager.clear_pending_specialist(session_id)
        session_manager.clear_pending_clarification(session_id)
        return "general"

    if session_manager.get_pending_clarification(session_id):
        return "clarify_answer"

    if session_manager.get_pending_specialist(session_id):
        return "provide_location"

    diet_words = [
        "diet", "meal plan", "nutrition", "food plan", "what should i eat",
        "diet plan", "meal", "eating plan"
    ]

    if _contains_word(query, diet_words):
        return "diet"

    lookup_words = [
        "hospital", "hospitals", "doctor", "doctors",
        "clinic", "clinics", "cardiologist", "specialist"
    ]

    if _contains_word(query, lookup_words):
        return "hospital_search"

    report_id = session_manager.get_report(session_id)

    if report_id is not None:
        return "report_chat"

    return "general"