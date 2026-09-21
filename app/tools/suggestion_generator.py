from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from app.llm.model import safe_invoke
from app.logging_config import get_logger

logger = get_logger(__name__)

# The answer is already written by the time this runs; the patient is only
# waiting on three optional chips. They used to go through the default
# retry policy - minutes, when the provider was rate limiting - so a
# finished answer could sit unsent. Now they get one short try.
SUGGESTION_BUDGET_SECONDS = 6

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="suggestions")

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

    prompt = SUGGESTION_PROMPT.format(query=query, answer=answer[:1500])

    try:
        future = _pool.submit(
            safe_invoke, prompt, max_retries=1, budget_seconds=SUGGESTION_BUDGET_SECONDS
        )
        response = future.result(timeout=SUGGESTION_BUDGET_SECONDS)

        lines = [
            line.strip("-•* ").strip()
            for line in (response.content or "").strip().split("\n")
            if line.strip()
        ]

        return lines[:3]

    except FuturesTimeout:
        # The thread finishes in the background; its result is discarded.
        logger.warning("Follow-up suggestions timed out; sending the answer without them")
        return []

    except Exception:
        logger.warning("Could not generate follow-up suggestions")
        return []
