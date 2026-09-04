import uuid

import pytest

from app.session.session_manager import SessionNotFound, session_manager


def _sid():
    return str(uuid.uuid4())


def test_messages_round_trip_in_order():

    sid = _sid()

    session_manager.add_message(sid, "user", "I have a headache")
    session_manager.add_message(sid, "assistant", "How long for?")

    messages = session_manager.get_messages(sid)

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "I have a headache"


def test_history_limit_returns_most_recent_oldest_first():

    sid = _sid()

    for i in range(10):
        session_manager.add_message(sid, "user", f"message {i}")

    messages = session_manager.get_messages(sid, limit=3)

    assert [m["content"] for m in messages] == ["message 7", "message 8", "message 9"]


def test_another_owner_cannot_read_a_session():

    sid = _sid()

    session_manager.add_message(sid, "user", "my haemoglobin is 9", owner="alice")
    session_manager.save_report(sid, "report-123", owner="alice")

    # The core IDOR: knowing the session id must not be enough.
    assert session_manager.get_messages(sid, owner="mallory") == []
    assert session_manager.get_report(sid, owner="mallory") is None
    assert session_manager.get_report_data(sid, owner="mallory") == {
        "analysis": [],
        "summary": "",
    }


def test_writing_to_someone_elses_session_is_rejected():

    sid = _sid()
    session_manager.add_message(sid, "user", "hello", owner="alice")

    with pytest.raises(SessionNotFound):
        session_manager.add_message(sid, "user", "hijack", owner="mallory")


def test_report_data_round_trip():

    sid = _sid()
    analysis = [{"report_type": "CBC", "parameters": {"Hb": {"value": "9", "status": "Low"}}}]

    session_manager.save_report_data(sid, analysis, "Low haemoglobin.")

    stored = session_manager.get_report_data(sid)

    assert stored["summary"] == "Low haemoglobin."
    assert stored["analysis"][0]["report_type"] == "CBC"


def test_pending_specialist_expires_after_ttl(monkeypatch):

    from app.session import session_manager as module

    sid = _sid()
    session_manager.set_pending_specialist(sid, "Cardiologist")

    assert session_manager.get_pending_specialist(sid) == "Cardiologist"

    # A failed doctor lookup used to leave this set forever, so every
    # later message was misread as a location reply.
    monkeypatch.setattr(module.settings, "pending_state_ttl_seconds", -1)

    assert session_manager.get_pending_specialist(sid) is None


def test_clear_chat_returns_report_id_for_cleanup():

    sid = _sid()
    session_manager.save_report(sid, "report-abc")

    assert session_manager.clear_chat(sid) == "report-abc"
    assert session_manager.get_report(sid) is None


def test_list_sessions_is_scoped_to_owner():

    owner = f"owner-{uuid.uuid4()}"
    sid = _sid()

    session_manager.set_chat_name(sid, "Blood work", owner=owner)

    listed = session_manager.list_sessions(owner=owner)

    assert [s["chat_name"] for s in listed] == ["Blood work"]
    assert session_manager.list_sessions(owner="somebody-else") == []
