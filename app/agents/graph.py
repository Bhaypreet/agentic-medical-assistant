"""The routing graph.

Every node reads state with .get() and the initial state is built by one
factory, because the invoke payload used to omit `specialist` while
doctor_node and ask_location_node read state["specialist"] directly. That
only worked because a single inbound edge happened to set it first - one
new edge into either node turned it into a KeyError at runtime.
"""

import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.diet_agents import diet_agent
from app.agents.report_agent import report_agent
from app.agents.report_chat_agent import report_chat_agent
from app.llm.model import safe_invoke
from app.logging_config import get_logger
from app.rag.chain import medical_rag
from app.session.session_manager import ANONYMOUS, session_manager
from app.supervisor.supervisor import classify_intent
from app.tools.doctor_finder import LookupFailed, find_doctors
from app.tools.severity_classifier import classify_severity

logger = get_logger(__name__)


class MedicalState(TypedDict, total=False):
    query: str
    pdf_path: str
    session_id: str
    owner: str
    report_id: str
    location: str
    severity: int
    emergency: bool
    specialist: str
    report_analysis: list
    response: str
    chat_history: list


def build_state(
    query: str,
    session_id: str,
    owner: str = ANONYMOUS,
    location: str = "",
    pdf_path: str = "",
    chat_history: list | None = None,
) -> MedicalState:
    """The one place an initial state is constructed, so every key exists."""

    return {
        "query": query,
        "pdf_path": pdf_path,
        "session_id": session_id,
        "owner": owner,
        "report_id": "",
        "location": location,
        "severity": 0,
        "emergency": False,
        "specialist": "",
        "report_analysis": [],
        "response": "",
        "chat_history": chat_history or [],
    }


def _ctx(state: MedicalState) -> tuple[str, str]:
    return state.get("session_id", ""), state.get("owner", ANONYMOUS)


# =====================================================
# SUPERVISOR
# =====================================================


def supervisor_node(state: MedicalState) -> str:

    session_id, owner = _ctx(state)

    intent = classify_intent(
        query=state.get("query", ""),
        session_id=session_id,
        pdf_path=state.get("pdf_path", ""),
        owner=owner,
    )

    logger.info("Routed message", extra={"intent": intent})

    return intent


# =====================================================
# GREETING
# =====================================================


GREETING = """Hello 👋

I am your AI Medical Assistant.

I can help you with:

- Medical questions
- Symptom analysis
- Blood report analysis (PDF or photo)
- Diet and nutrition plans
- Chat with an uploaded report
- Finding nearby hospitals and clinics

If you think you are having a medical emergency, call your local emergency
number instead of using this chat."""


def greeting_node(state: MedicalState) -> dict[str, Any]:
    return {"response": GREETING}


# =====================================================
# CLARIFICATION - one follow-up question before triage
# =====================================================


CLARIFY_FALLBACK = (
    "How long have you had this, and is there anything else you're feeling alongside it?"
)


def ask_clarification_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)
    query = state.get("query", "")

    session_manager.set_pending_clarification(session_id, query, owner=owner)

    prompt = f"""A patient just said: "{query}"

Ask exactly ONE short, natural follow-up question a doctor would ask before
triaging this (e.g. how long, severity 1-10, any other symptoms). Respond
in the SAME language the patient used. Return ONLY the question, nothing
else."""

    try:
        question = safe_invoke(prompt).content.strip()
    except Exception:
        logger.exception("Clarification question generation failed")
        question = CLARIFY_FALLBACK

    return {"response": question or CLARIFY_FALLBACK}


def clarify_answer_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)

    original = session_manager.get_pending_clarification(session_id, owner=owner)
    session_manager.clear_pending_clarification(session_id, owner=owner)

    combined = f"{original}. Additional details: {state.get('query', '')}" if original else state.get("query", "")

    result = classify_severity(combined)

    conditions = ", ".join(result.get("possible_conditions") or []) or "Not enough information yet"

    response = f"""## Assessment

**Risk level:** {result['risk_level']}

**Suggested specialist:** {result['specialist']}

**Possible causes:** {conditions}

**Why:** {result['reasoning']}"""

    return {
        "query": combined,
        "severity": result["severity"],
        "emergency": result["emergency"],
        "specialist": result["specialist"],
        "response": response,
    }


# =====================================================
# GENERAL KNOWLEDGE / DIET
# =====================================================


def rag_node(state: MedicalState) -> dict[str, Any]:
    return {"response": medical_rag(state.get("query", ""), chat_history=state.get("chat_history"))}


def diet_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)

    return {
        "response": diet_agent(
            session_id=session_id,
            query=state.get("query", ""),
            chat_history=state.get("chat_history"),
            owner=owner,
        )
    }


# =====================================================
# FACILITY LOOKUP
# =====================================================


LOOKUP_UNAVAILABLE = (
    "⚠️ I couldn't reach the hospital directory just now. Please try again in a "
    "moment - and if this feels urgent, call your local emergency number rather "
    "than waiting."
)


def _keep_assessment(state: MedicalState, addition: str) -> str:
    """Append to the triage assessment rather than discarding it.

    Routing from clarify_answer_node used to overwrite `response`, so the
    patient never saw the risk level that triggered the escalation.
    """

    existing = (state.get("response") or "").strip()

    return f"{existing}\n\n---\n\n{addition}" if existing else addition


def ask_location_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)
    specialist = state.get("specialist") or "General Physician"

    session_manager.set_pending_specialist(session_id, specialist, owner=owner)

    return {
        "response": _keep_assessment(
            state,
            f"A **{specialist}** is the right person to see for this.\n\n"
            f"📍 Reply with your city or area and I'll find nearby options.",
        )
    }


def _lookup(location: str, specialist: str) -> dict[str, Any]:
    """Shared lookup so every entry point handles failure the same way."""

    try:
        doctors = find_doctors(location, specialist)
    except LookupFailed:
        logger.warning("Facility lookup unavailable")
        return {"response": LOOKUP_UNAVAILABLE, "found": False, "reachable": False}
    except Exception:
        logger.exception("Facility lookup failed unexpectedly")
        return {"response": LOOKUP_UNAVAILABLE, "found": False, "reachable": False}

    return {
        "response": _format_doctor_response(doctors, specialist, location),
        "found": bool(doctors),
        "reachable": True,
    }


def doctor_node(state: MedicalState) -> dict[str, Any]:

    specialist = state.get("specialist") or "General Physician"
    outcome = _lookup(state.get("location", ""), specialist)

    return {"response": _keep_assessment(state, outcome["response"])}


def resume_doctor_node(state: MedicalState) -> dict[str, Any]:
    """Handle the patient's reply to "which city are you in?"."""

    session_id, owner = _ctx(state)

    specialist = session_manager.get_pending_specialist(session_id, owner=owner)

    if not specialist:
        return {
            "response": (
                "Sorry - I've lost track of what we were looking for. "
                "Could you describe your symptom again?"
            )
        }

    location = re.sub(
        r"(?i)^(my location is|i am in|i'm in|located at|location is|i am at|in)\s*",
        "",
        state.get("query", ""),
    ).strip(" .?!")

    outcome = _lookup(location, specialist)

    # Previously this only cleared on success, so a lookup that returned
    # nothing left the session waiting for a location forever and every
    # later message was misread as a location reply. Clear it whenever the
    # directory answered at all; keep waiting only if it was unreachable.
    if outcome["reachable"]:
        session_manager.clear_pending_specialist(session_id, owner=owner)

    return {"response": outcome["response"]}


_GENERIC_TERMS = {
    "hospital", "hospitals", "doctor", "doctors", "clinic", "clinics",
    "specialist", "cardiologist", "dermatologist", "dentist", "neurologist",
    "orthopedic", "gynecologist", "pediatrician", "ent specialist", "me", "us",
    "here", "somewhere",
}

_SPECIALISTS = [
    "cardiologist", "dermatologist", "dentist", "neurologist",
    "orthopedic", "gynecologist", "pediatrician", "ent specialist",
]


def _extract_location_from_query(query: str) -> str:

    match = re.search(r"(?:near|nearby|in|at|around)\s+(.+)", query, re.IGNORECASE)

    if not match:
        return ""

    candidate = match.group(1).strip(" .?!")
    words = candidate.lower().split()

    if not words or all(word in _GENERIC_TERMS for word in words):
        return ""

    return candidate


def hospital_search_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)
    query = state.get("query", "")

    specialist = next((word for word in _SPECIALISTS if word in query.lower()), "hospital")

    location = _extract_location_from_query(query)

    if not location:
        session_manager.set_pending_specialist(session_id, specialist, owner=owner)
        return {"response": "📍 Sure - which city or area should I search near?"}

    return {"response": _lookup(location, specialist)["response"]}


def _format_doctor_response(doctors: list[dict], specialist: str, location: str) -> str:

    if not doctors:
        return (
            f"I couldn't find any {specialist}s listed near **{location}**.\n\n"
            "The directory's coverage varies by area - try a nearby larger town "
            "or city name."
        )

    lines = [f"## {specialist.title()}s near {location}\n"]

    for doctor in doctors:
        lat = doctor["location"]["lat"]
        lng = doctor["location"]["lng"]

        lines.append(f"🏥 **{doctor['name']}** — {doctor['distance_km']} km away")
        lines.append(f"📍 {doctor['address']}")

        if doctor.get("phone"):
            lines.append(f"📞 {doctor['phone']}")

        lines.append(f"🗺 https://www.google.com/maps/search/?api=1&query={lat},{lng}\n")

    lines.append(
        "_Listings come from OpenStreetMap and may be out of date. "
        "Please call ahead to confirm._"
    )

    return "\n".join(lines)


# =====================================================
# REPORTS
# =====================================================


def report_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)

    result = report_agent(
        file_path=state.get("pdf_path", ""),
        session_id=session_id,
        owner=owner,
    )

    return {
        "report_analysis": result["analysis"],
        "report_id": result["report_id"],
        "response": result["summary"],
    }


def report_chat_node(state: MedicalState) -> dict[str, Any]:

    session_id, owner = _ctx(state)

    return {
        "response": report_chat_agent(
            session_id=session_id,
            question=state.get("query", ""),
            chat_history=state.get("chat_history"),
            owner=owner,
        )
    }


# =====================================================
# SEVERITY ROUTING
# =====================================================


def severity_router(state: MedicalState) -> str:

    if state.get("severity", 0) <= 2:
        return "rag"

    return "doctor" if state.get("location") else "ask_location"


# =====================================================
# GRAPH
# =====================================================


def _build_graph():

    builder = StateGraph(MedicalState)

    builder.add_node("greeting_node", greeting_node)
    builder.add_node("ask_clarification_node", ask_clarification_node)
    builder.add_node("clarify_answer_node", clarify_answer_node)
    builder.add_node("rag_node", rag_node)
    builder.add_node("diet_node", diet_node)
    builder.add_node("doctor_node", doctor_node)
    builder.add_node("ask_location_node", ask_location_node)
    builder.add_node("resume_doctor_node", resume_doctor_node)
    builder.add_node("hospital_search_node", hospital_search_node)
    builder.add_node("report_node", report_node)
    builder.add_node("report_chat_node", report_chat_node)

    builder.add_conditional_edges(
        START,
        supervisor_node,
        {
            "greeting": "greeting_node",
            "symptom": "ask_clarification_node",
            "clarify_answer": "clarify_answer_node",
            "report_upload": "report_node",
            "report_chat": "report_chat_node",
            "provide_location": "resume_doctor_node",
            "hospital_search": "hospital_search_node",
            "diet": "diet_node",
            "general": "rag_node",
        },
    )

    builder.add_conditional_edges(
        "clarify_answer_node",
        severity_router,
        {
            "rag": "rag_node",
            "doctor": "doctor_node",
            "ask_location": "ask_location_node",
        },
    )

    for node in (
        "greeting_node",
        "ask_clarification_node",
        "rag_node",
        "diet_node",
        "doctor_node",
        "ask_location_node",
        "resume_doctor_node",
        "hospital_search_node",
        "report_node",
        "report_chat_node",
    ):
        builder.add_edge(node, END)

    return builder.compile()


graph = _build_graph()
