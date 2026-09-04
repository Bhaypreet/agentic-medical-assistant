from app.llm.model import safe_invoke
from app.logging_config import get_logger
from app.report_rag.retriever import ReportStoreMissing, get_report_retriever

logger = get_logger(__name__)

PROMPT = """You are a friendly, conversational medical assistant chatting with a patient about their
uploaded lab report - like ChatGPT, but with access to their personal data.

Previous conversation:
{history}

Structured, already-verified data extracted from the patient's report (this is your
primary and most reliable source - always prefer this over the raw excerpts below):
{structured_data}

Raw excerpts from the report (secondary/supplementary source, may be incomplete or
out of order - use only if the structured data above doesn't cover the question):
{raw_context}

FORMATTING RULES (important):
- NEVER answer in one long paragraph.
- Use markdown: short headers, bullet points, numbered steps, or a table wherever it fits
  (tables are great for lab values: Test | Result | Normal Range | Meaning).
- Keep each bullet/line short and scannable.
- Bold key values and abnormal findings.

LANGUAGE RULE:
- Respond in the SAME language the patient's question is written in.

SAFETY RULES:
- A value marked "Unknown" could not be interpreted. Say so plainly and suggest the
  patient confirm it with their clinician. NEVER describe an Unknown value as normal.
- Never state a diagnosis as fact - describe what the values suggest and what a
  clinician would check next.

Instructions:
- Answer directly and specifically using the structured data whenever it's relevant.
- If the question is a general health question not covered by either source,
  answer using your own general medical knowledge instead of refusing.
- Do not say things like "I don't see numerical values" if the structured data
  above actually contains them - always check structured data first.

Question:
{question}

Answer:
"""


def _format_history(chat_history, limit=6):

    if not chat_history:
        return ""

    return "\n".join(f"{m['role']}: {m['content']}" for m in chat_history[-limit:])


def _raw_excerpts(report_id: str, question: str) -> str:
    """Passages from the report's own index, or an empty string.

    A missing or unreadable index degrades to structured-data-only rather
    than failing the request.
    """

    try:
        docs = get_report_retriever(report_id).invoke(question)
    except (ReportStoreMissing, ValueError):
        logger.warning("Report index unavailable; answering from structured data only")
        return ""
    except Exception:
        logger.exception("Report retrieval failed; answering from structured data only")
        return ""

    return "\n\n".join(doc.page_content for doc in docs)


def chat_with_report(report_id: str, question: str, structured_data=None, chat_history=None):

    structured_text = ""

    if structured_data:
        summary = structured_data.get("summary", "")
        analysis = structured_data.get("analysis", [])
        structured_text = f"Summary:\n{summary}\n\nDetailed Analysis:\n{analysis}"

    prompt = PROMPT.format(
        raw_context=_raw_excerpts(report_id, question),
        structured_data=structured_text or "No structured data was extracted.",
        question=question,
        history=_format_history(chat_history),
    )

    return safe_invoke(prompt).content
