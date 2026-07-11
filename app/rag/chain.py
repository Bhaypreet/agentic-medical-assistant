from app.llm.model import safe_invoke
from app.rag.retriever import medical_retriever


def _format_history(chat_history, limit=6):
    if not chat_history:
        return ""
    recent = chat_history[-limit:]
    return "\n".join(f"{m['role']}: {m['content']}" for m in recent)


def medical_rag(query, chat_history=None):

    docs = medical_retriever.invoke(query)

    context = "\n\n".join(doc.page_content for doc in docs)
    history_text = _format_history(chat_history or [])

    prompt = f"""
You are a friendly, conversational medical assistant - like ChatGPT, but focused on health.
Keep continuity with the earlier conversation below.

FORMATTING RULES:
- NEVER answer in one long paragraph.
- Use markdown: short headers, bullet points, numbered steps, or tables.
- Bold key terms and values.

LANGUAGE RULE:
- Respond in the SAME language the user's current question is written in
  (English, Hindi, Hinglish, Punjabi, etc.) - match their language naturally.

SAFETY RULE:
- NEVER invent or guess specific real-world doctor names, hospital names, or
  phone numbers. Tell the user to share their location instead.

Previous conversation:
{history_text}

Reference knowledge (use if relevant, otherwise use your own general medical knowledge):
{context}

Current question:
{query}
"""

    response = safe_invoke(prompt)

    return response.content