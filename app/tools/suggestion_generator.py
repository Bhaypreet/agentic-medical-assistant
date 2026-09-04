from app.llm.model import safe_invoke
from app.logging_config import get_logger

logger = get_logger(__name__)

SUGGESTION_PROMPT = """Based on this medical assistant conversation, suggest exactly 3 short,
natural follow-up questions the patient might genuinely want to ask next.

Last question: {query}
Assistant's answer: {answer}

Rules:
- Each suggestion must be under 8 words
- Make them genuinely useful next steps - e.g. asking to elaborate on a specific value,
  asking about diet/exercise specifics, asking to generate/download a full report,
  asking about nearby doctors, asking what to do next
- Return ONLY the 3 questions, one per line, no numbering, no extra text, no quotes
"""


def generate_suggestions(query: str, answer: str) -> list[str]:
    """Follow-up prompts for the UI.

    Best-effort: this is the second model call per chat turn, so it never
    fails the request and returns nothing when the model is unavailable.
    """

    try:
        response = safe_invoke(SUGGESTION_PROMPT.format(query=query, answer=answer[:1500]))

        lines = [
            line.strip("-•* ").strip()
            for line in (response.content or "").strip().split("\n")
            if line.strip()
        ]

        return lines[:3]

    except Exception:
        logger.warning("Could not generate follow-up suggestions")
        return []
