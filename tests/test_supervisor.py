import uuid

from app.session.session_manager import session_manager
from app.supervisor.supervisor import classify_intent


def _new_session():
    return str(uuid.uuid4())


# ----------------------------------------------------------------- greetings


def test_bare_greeting_is_a_greeting():
    assert classify_intent("hi there", _new_session()) == "greeting"


def test_greeting_substring_is_not_a_greeting():
    # "something" contains "hi" as a substring.
    assert classify_intent("suggest me something", _new_session()) != "greeting"


def test_greeting_followed_by_a_symptom_is_a_symptom():
    # Greetings used to be checked before symptoms, so this classified as
    # a greeting - and the greeting branch also cleared pending triage.
    assert (
        classify_intent("hey, I've had crushing chest pain since morning", _new_session())
        == "symptom"
    )


def test_greeting_with_other_content_is_not_a_greeting():
    assert (
        classify_intent("hello, can you find me a hospital in Delhi", _new_session())
        == "hospital_search"
    )


# ----------------------------------------------------------------- symptoms


def test_first_person_symptom_is_triaged():
    assert classify_intent("I have a severe headache", _new_session()) == "symptom"


def test_informational_phrasing_about_own_symptom_is_triaged():
    # "explain my chest pain" used to hit the informational check first
    # and skip the severity classifier entirely.
    assert classify_intent("explain my chest pain", _new_session()) == "symptom"
    assert classify_intent("why does my head hurt so much", _new_session()) == "symptom"


def test_general_question_about_a_symptom_is_not_triaged():
    assert classify_intent("what is chest pain", _new_session()) == "general"
    assert classify_intent("what causes headache", _new_session()) == "general"
    assert classify_intent("tell me about fever in children", _new_session()) == "general"


def test_new_symptom_interrupts_a_pending_location_wait():

    session_id = _new_session()
    session_manager.set_pending_specialist(session_id, "Cardiologist")

    assert classify_intent("I have severe stomach pain now", session_id) == "symptom"
    assert session_manager.get_pending_specialist(session_id) is None


def test_new_symptom_interrupts_a_pending_clarification():

    session_id = _new_session()
    session_manager.set_pending_clarification(session_id, "my knee hurts")

    assert classify_intent("I also have a fever", session_id) == "symptom"
    assert session_manager.get_pending_clarification(session_id) is None


# ----------------------------------------------------------- pending flows


def test_pending_specialist_routes_a_bare_location_reply():

    session_id = _new_session()
    session_manager.set_pending_specialist(session_id, "Cardiologist")

    assert classify_intent("Chandigarh", session_id) == "provide_location"


def test_pending_clarification_routes_a_follow_up_answer():

    session_id = _new_session()
    session_manager.set_pending_clarification(session_id, "chest pain")

    assert classify_intent("about three days, quite bad", session_id) == "clarify_answer"


def test_cancelling_clears_pending_state():

    session_id = _new_session()
    session_manager.set_pending_specialist(session_id, "Cardiologist")

    assert classify_intent("never mind", session_id) == "general"
    assert session_manager.get_pending_specialist(session_id) is None


# ------------------------------------------------------------------- other


def test_hospital_lookup_detected():
    assert classify_intent("suggest me nearby hospitals", _new_session()) == "hospital_search"


def test_diet_request_detected():
    assert classify_intent("give me a diet plan", _new_session()) == "diet"


def test_upload_takes_priority():
    assert classify_intent("anything", _new_session(), pdf_path="/tmp/x.pdf") == "report_upload"


def test_general_question_fallback():
    assert classify_intent("what is fever", _new_session()) == "general"


def test_empty_message_does_not_crash():
    assert classify_intent("", _new_session()) == "general"
    assert classify_intent("   ", _new_session()) == "general"


def test_report_questions_route_to_report_chat_once_one_is_uploaded():

    session_id = _new_session()
    session_manager.save_report(session_id, str(uuid.uuid4()))

    assert classify_intent("why is my hemoglobin low", session_id) == "report_chat"


# ---------------------------------------------------------- other languages


def test_hindi_symptom_is_triaged():
    # Devanagari has no Latin word boundaries, so these are matched as
    # substrings; matching English only meant they were never triaged.
    assert classify_intent("मुझे बुखार है", _new_session()) == "symptom"


def test_romanised_hindi_symptom_is_triaged():
    assert classify_intent("mujhe bahut sir dard ho raha hai", _new_session()) == "symptom"


def test_punjabi_symptom_is_triaged():
    assert classify_intent("ਮੈਨੂੰ ਬੁਖਾਰ ਹੈ", _new_session()) == "symptom"


def test_hindi_hospital_lookup_is_detected():
    assert classify_intent("दिल्ली में अस्पताल", _new_session()) == "hospital_search"
