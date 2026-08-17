from app.llm.model import safe_invoke
from app.session.session_manager import ANONYMOUS, session_manager

DIET_PROMPT = """You are a certified nutrition counsellor talking to a patient.

{report_context}

Previous conversation:
{history}

Patient's question: {query}

Instructions:
- Keep continuity with the conversation above - don't repeat things already said.
- If report data is available above, build the diet plan AROUND the specific
  abnormal values (e.g. high blood sugar -> low-glycemic foods, low vitamin D
  -> fortified foods + sun exposure, high triglycerides -> low saturated fat).
- Ignore any value whose status is "Unknown" - it could not be interpreted, so
  never build advice on it, and never describe it as normal.
- If no report data is available, give solid general nutrition advice based
  on the question.
- Format as markdown: short headers, bullet points, or a simple meal table
  (Breakfast/Lunch/Dinner/Snacks). Never write long paragraphs.
- Respond in the same language the patient used in their question.
"""


def diet_agent(session_id: str, query: str, chat_history=None, owner: str = ANONYMOUS) -> str:

    report_data = session_manager.get_report_data(session_id, owner=owner)
    analysis = report_data.get("analysis", [])

    if analysis:
        report_context = (
            f"Patient's lab report findings (use these to personalise the plan):\n{analysis}"
        )
    else:
        report_context = (
            "No lab report has been uploaded - give general, sensible nutrition advice."
        )

    history_text = ""

    if chat_history:
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in chat_history[-6:])

    prompt = DIET_PROMPT.format(
        report_context=report_context,
        history=history_text,
        query=query,
    )

    return safe_invoke(prompt).content
