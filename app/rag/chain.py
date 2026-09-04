from app.llm.model import safe_invoke
from app.logging_config import get_logger
from app.rag.retriever import KnowledgeBaseUnavailable, get_medical_retriever

logger = get_logger(__name__)

PROMPT = """You are a friendly, conversational medical assistant - like ChatGPT, but focused on health.
Keep continuity with the earlier conversation below.

FORMATTING RULES:
- NEVER answer in one long paragraph.
- Use markdown: short headers, bullet points, numbered steps, or tables.
- Bold key terms and values.

LANGUAGE RULE:
- Respond in the SAME language the user's current question is written in
  (English, Hindi, Hinglish, Punjabi, etc.) - match their language naturally.

SAFETY RULES:
- NEVER invent or guess specific real-world doctor names, hospital names, or
  phone numbers. Tell the user to share their location instead.
- NEVER state a diagnosis as fact. Describe possibilities and say what would
  need to be checked by a clinician.
- If the question describes symptoms that could be an emergency, say so first.

Previous conversation:
{history}

Reference knowledge (use if relevant, otherwise use your own general medical knowledge):
{context}

Current question:
{query}
"""


def _format_history(chat_history, limit=6):

    if not chat_history:
        return ""

    recent = chat_history[-limit:]

    return "\n".join(f"{m['role']}: {m['content']}" for m in recent)


def _retrieve(query: str) -> str:
    """Reference passages for the query, or an empty string.

    A knowledge base that failed to load degrades the answer rather than
    failing the request - the model still has its own general knowledge.
    """

    try:
        docs = get_medical_retriever().invoke(query)
    except KnowledgeBaseUnavailable:
        logger.warning("Answering without the knowledge base; it is not loaded")
        return ""
    except Exception:
        logger.exception("Retrieval failed; answering without reference passages")
        return ""

    return "\n\n".join(doc.page_content for doc in docs)


def medical_rag(query, chat_history=None):

    prompt = PROMPT.format(
        history=_format_history(chat_history or []),
        context=_retrieve(query),
        query=query,
    )

    return safe_invoke(prompt).content
