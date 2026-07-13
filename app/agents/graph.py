import re
from typing import TypedDict

from langgraph.graph import StateGraph
from langgraph.graph import START, END

from app.supervisor.supervisor import classify_intent
from app.session.session_manager import session_manager

from app.tools.severity_classifier import classify_severity
from app.tools.doctor_finder import find_doctors
from app.llm.model import safe_invoke

from app.rag.chain import medical_rag

from app.agents.report_agent import report_agent
from app.agents.report_chat_agent import report_chat_agent
from app.agents.diet_agents import diet_agent


# =====================================================
# STATE
# =====================================================

class MedicalState(TypedDict):
    query: str
    pdf_path: str

    session_id: str
    report_id: str

    location: str

    severity: int
    specialist: str

    report_analysis: list

    response: str

    chat_history: list


# =====================================================
# SUPERVISOR
# =====================================================

def supervisor_node(state: MedicalState):

    return classify_intent(
        query=state["query"],
        session_id=state["session_id"],
        pdf_path=state["pdf_path"]
    )


# =====================================================
# GREETING
# =====================================================

def greeting_node(state: MedicalState):

    return {
        "response": """
Hello 👋

I am your AI Medical Assistant.

I can help you with:

- Medical Questions
- Symptom Analysis
- Blood Report Analysis (PDF or photo)
- Diet & Nutrition Plans
- Chat with Uploaded Reports
- Doctor Recommendations
"""
    }


# =====================================================
# CLARIFICATION - agent asks ONE follow-up question
# before triaging, like a real doctor would
# =====================================================

def ask_clarification_node(state: MedicalState):

    session_id = state["session_id"]
    query = state["query"]

    session_manager.set_pending_clarification(session_id, query)

    prompt = f"""A patient just said: "{query}"

Ask exactly ONE short, natural follow-up question a doctor would ask before
triaging this (e.g. how long, severity 1-10, any other symptoms). Respond
in the SAME language the patient used. Return ONLY the question, nothing
else."""

    try:
        question = safe_invoke(prompt).content.strip()
    except Exception:
        question = "How long have you had this, and is there anything else you're feeling alongside it?"

    return {"response": question}


def clarify_answer_node(state: MedicalState):

    session_id = state["session_id"]

    original_query = session_manager.get_pending_clarification(session_id)
    session_manager.clear_pending_clarification(session_id)

    combined_query = f"{original_query}. Additional details: {state['query']}"

    result = classify_severity(combined_query)

    return {
        "query": combined_query,
        "severity": result["severity"],
        "specialist": result["specialist"],
        "response": f"""
Risk Level: {result['risk_level']}

Emergency: {result['emergency']}

Recommended Specialist:
{result['specialist']}

Possible Conditions:
{", ".join(result['possible_conditions'])}

Reason:
{result['reasoning']}
"""
    }


# =====================================================
# MEDICAL RAG (general questions)
# =====================================================

def rag_node(state: MedicalState):

    answer = medical_rag(
        state["query"],
        chat_history=state.get("chat_history", [])
    )

    return {"response": answer}


# =====================================================
# DIET / NUTRITION AGENT
# =====================================================

def diet_node(state: MedicalState):

    answer = diet_agent(
        session_id=state["session_id"],
        query=state["query"],
        chat_history=state.get("chat_history", [])
    )

    return {"response": answer}


# =====================================================
# ASK FOR LOCATION
# (severity is high, but we don't have a location yet)
# =====================================================

def ask_location_node(state: MedicalState):

    specialist = state["specialist"]

    session_manager.set_pending_specialist(state["session_id"], specialist)

    return {
        "response": f"""⚠️ This sounds like it could be serious — a **{specialist}** is recommended.

📍 Please reply with your current location (city or area) so I can find nearby {specialist}s for you.
"""
    }


# =====================================================
# DOCTOR FINDER (severity high + location already given)
# =====================================================

def doctor_node(state: MedicalState):

    specialist = state["specialist"]
    location = state["location"]

    try:
        doctors = find_doctors(location, specialist)
    except Exception as e:
        return {"response": f"⚠️ Could not fetch nearby doctors right now ({e}). Please try again."}

    return {"response": _format_doctor_response(doctors, specialist)}


# =====================================================
# RESUME DOCTOR FINDER
# (user just replied with their location after being asked)
# =====================================================

def resume_doctor_node(state: MedicalState):

    session_id = state["session_id"]

    specialist = session_manager.get_pending_specialist(session_id)

    raw_location = state["query"]
    location = re.sub(
        r"(?i)^(my location is|i am in|i'm in|located at|location is|i am at)\s*",
        "",
        raw_location
    ).strip(" .?!")

    if not specialist:
        return {"response": "I lost track of what specialist we needed - could you describe your symptom again?"}

    try:
        doctors = find_doctors(location, specialist)
    except Exception as e:
        return {"response": f"⚠️ Could not fetch nearby doctors right now ({e}). Please try again."}

    if doctors:
        session_manager.clear_pending_specialist(session_id)

    return {"response": _format_doctor_response(doctors, specialist)}


# =====================================================
# EXPLICIT HOSPITAL/DOCTOR SEARCH
# (user directly asks "hospitals near X" / "doctor near me" etc,
# with no prior severity flow - always uses the real Maps tool,
# never lets the LLM invent names)
# =====================================================

_GENERIC_TERMS = {
    "hospital", "hospitals", "doctor", "doctors", "clinic", "clinics",
    "specialist", "cardiologist", "dermatologist", "dentist", "neurologist",
    "orthopedic", "gynecologist", "pediatrician", "ent specialist", "me", "us"
}


def _extract_location_from_query(query: str) -> str:

    match = re.search(r"(?:near|nearby|in|at|around)\s+(.+)", query, re.IGNORECASE)

    if not match:
        return ""

    candidate = match.group(1).strip(" .?!").lower()

    if candidate in _GENERIC_TERMS:
        return ""

    words = candidate.split()
    if words and all(w in _GENERIC_TERMS for w in words):
        return ""

    return match.group(1).strip(" .?!")


def hospital_search_node(state: MedicalState):

    query = state["query"]

    specialist = "hospital"
    for word in ["cardiologist", "dermatologist", "dentist", "neurologist",
                 "orthopedic", "gynecologist", "pediatrician", "ent specialist"]:
        if word in query.lower():
            specialist = word
            break

    location = _extract_location_from_query(query)

    if not location:
        session_manager.set_pending_specialist(state["session_id"], specialist)
        return {"response": "📍 Sure - which city/area should I search near?"}

    try:
        doctors = find_doctors(location, specialist)
    except Exception as e:
        return {"response": f"⚠️ Could not fetch nearby results right now ({e}). Please try again."}

    return {"response": _format_doctor_response(doctors, specialist)}


def _format_doctor_response(doctors, specialist):

    if len(doctors) == 0:
        return f"No nearby {specialist}s found. Please try a nearby bigger city/area name."

    response = f"## Recommended {specialist.title()}s Near You\n\n"

    for doctor in doctors:
        lat = doctor["location"]["lat"]
        lng = doctor["location"]["lng"]
        maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

        response += (
            f"🏥 **{doctor['name']}**\n"
            f"⭐ Rating: {doctor['rating']}\n"
            f"📍 {doctor['address']}\n"
            f"🗺 {maps_link}\n\n"
        )

    return response


# =====================================================
# REPORT UPLOAD
# =====================================================

def report_node(state: MedicalState):

    result = report_agent(
        file_path=state["pdf_path"],
        session_id=state["session_id"]
    )

    return {
        "report_analysis": result["analysis"],
        "report_id": result["report_id"]
    }


# =====================================================
# REPORT CHAT
# =====================================================

def report_chat_node(state: MedicalState):

    answer = report_chat_agent(
        session_id=state["session_id"],
        question=state["query"],
        chat_history=state.get("chat_history", [])
    )

    return {"response": answer}


# =====================================================
# SEVERITY ROUTER
# =====================================================

def severity_router(state: MedicalState):

    if state["severity"] <= 2:
        return "rag"
    if state.get("location"):
        return "doctor"
    return "ask_location"


# =====================================================
# GRAPH
# =====================================================

graph_builder = StateGraph(MedicalState)


# ---------------- Nodes ----------------

graph_builder.add_node("greeting_node", greeting_node)
graph_builder.add_node("ask_clarification_node", ask_clarification_node)
graph_builder.add_node("clarify_answer_node", clarify_answer_node)
graph_builder.add_node("rag_node", rag_node)
graph_builder.add_node("diet_node", diet_node)
graph_builder.add_node("doctor_node", doctor_node)
graph_builder.add_node("ask_location_node", ask_location_node)
graph_builder.add_node("resume_doctor_node", resume_doctor_node)
graph_builder.add_node("hospital_search_node", hospital_search_node)
graph_builder.add_node("report_node", report_node)
graph_builder.add_node("report_chat_node", report_chat_node)


# ---------------- Start Routing ----------------

graph_builder.add_conditional_edges(
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
        "general": "rag_node"
    }
)


# ---------------- Severity Routing (after clarification) ----------------

graph_builder.add_conditional_edges(
    "clarify_answer_node",
    severity_router,
    {
        "rag": "rag_node",
        "doctor": "doctor_node",
        "ask_location": "ask_location_node"
    }
)


# ---------------- End ----------------

graph_builder.add_edge("greeting_node", END)
graph_builder.add_edge("ask_clarification_node", END)
graph_builder.add_edge("rag_node", END)
graph_builder.add_edge("diet_node", END)
graph_builder.add_edge("doctor_node", END)
graph_builder.add_edge("ask_location_node", END)
graph_builder.add_edge("resume_doctor_node", END)
graph_builder.add_edge("hospital_search_node", END)
graph_builder.add_edge("report_node", END)
graph_builder.add_edge("report_chat_node", END)


graph = graph_builder.compile()