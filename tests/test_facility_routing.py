"""Facility requests reach the facility lookup, with the right place.

"nearby hospital in Mumbai" used to send "hospital in Mumbai" to the
geocoder, and a chat still waiting on a clarification read "hospitals in
Delhi" as the answer to that instead of a request for hospitals.
"""

import uuid

import pytest

from app.session.session_manager import session_manager
from app.supervisor.supervisor import classify_intent
from app.tools.location import extract_location


@pytest.mark.parametrize(
    ("query", "place"),
    [
        ("Find hospitals in Delhi", "Delhi"),
        ("nearby hospital in Mumbai", "Mumbai"),
        ("show me hospitals near Chandigarh", "Chandigarh"),
        ("hospitals in Ropar Punjab", "Ropar Punjab"),
        ("Find a cardiologist in Bangalore", "Bangalore"),
        ("I need a doctor in Pune please", "Pune"),
        ("best hospitals in Delhi for heart problems", "Delhi"),
        ("clinics near Connaught Place, Delhi", "Connaught Place, Delhi"),
        ("hospitals near me in Jaipur", "Jaipur"),
    ],
)
def test_the_place_is_extracted(query, place):
    assert extract_location(query) == place


@pytest.mark.parametrize(
    "query",
    ["find a hospital near me", "hospitals nearby", "I need a doctor", "find clinic", ""],
)
def test_no_place_means_no_place(query):
    assert extract_location(query) == ""


def test_prepositions_inside_words_do_not_count():
    """'in' sits inside "find" and "clinic"."""

    assert extract_location("find clinics") == ""


def _session():
    return str(uuid.uuid4()), "owner-" + uuid.uuid4().hex[:8]


@pytest.mark.parametrize(
    "query",
    ["Find hospitals in Delhi", "nearby hospital in Mumbai", "Find a cardiologist in Bangalore"],
)
def test_a_facility_request_with_a_place_routes_to_the_lookup(query):
    sid, owner = _session()
    assert classify_intent(query, sid, owner=owner) == "hospital_search"


def test_a_pending_clarification_does_not_swallow_a_facility_request():
    sid, owner = _session()
    session_manager.set_pending_clarification(sid, "I have a mild headache", owner=owner)

    assert classify_intent("hospitals in Delhi", sid, owner=owner) == "hospital_search"
    assert session_manager.get_pending_clarification(sid, owner=owner) is None


def test_a_pending_location_wait_does_not_swallow_a_new_search():
    sid, owner = _session()
    session_manager.set_pending_specialist(sid, "Cardiologist", owner=owner)

    assert classify_intent("find hospitals in Pune", sid, owner=owner) == "hospital_search"


def test_a_red_flag_still_goes_to_triage_first():
    """Triage escalates; a list of hospitals does not."""

    sid, owner = _session()
    query = "crushing chest pain radiating to my left arm, find a hospital in Delhi"

    assert classify_intent(query, sid, owner=owner) == "symptom"


def test_without_a_place_the_lookup_still_asks_for_one():
    sid, owner = _session()
    assert classify_intent("find a hospital near me", sid, owner=owner) == "hospital_search"
