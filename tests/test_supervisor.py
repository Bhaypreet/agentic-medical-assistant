import uuid

from app.supervisor.supervisor import classify_intent
from app.session.session_manager import session_manager


def _new_session():
    return str(uuid.uuid4())


def test_greeting_detected_as_whole_word():

    session_id = _new_session()
    assert classify_intent("hi there", session_id) == "greeting"


def test_greeting_substring_bug_stays_fixed():

    session_id = _new_session()

    # "something" contains "hi" as a substring - this must NOT be
    # mistaken for a greeting (this was a real bug we fixed earlier)
    assert classify_intent("suggest me something", session_id) != "greeting"


def test_symptom_detected():

    session_id = _new_session()
    assert classify_intent("I have a severe headache", session_id) == "symptom"


def test_pending_specialist_routes_to_provide_location():

    session_id = _new_session()

    session_manager.set_pending_specialist(session_id, "Cardiologist")
    assert classify_intent("Chandigarh", session_id) == "provide_location"

    session_manager.clear_pending_specialist(session_id)


def test_new_symptom_overrides_pending_location_wait():

    session_id = _new_session()

    session_manager.set_pending_specialist(session_id, "Cardiologist")

    # a genuinely new symptom should interrupt the "waiting for location"
    # state instead of being swallowed as a location reply
    assert classify_intent("I have severe headache", session_id) == "symptom"


def test_hospital_lookup_detected():

    session_id = _new_session()
    assert classify_intent("suggest me nearby hospitals", session_id) == "hospital_search"


def test_general_question_fallback():

    session_id = _new_session()
    assert classify_intent("what is fever", session_id) == "general"