"""Access to the language model.

The client used to be constructed at module import with no timeout, and
safe_invoke retried only rate limits - any other failure propagated
immediately, and the final failure raised a bare Exception that surfaced
as an unstructured 500.
"""

import random
import re
import threading
import time

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_model = None


class LLMUnavailable(RuntimeError):
    """The model could not be reached after exhausting retries."""


def get_model():
    """Build the chat model on first use, then reuse it."""

    global _model

    if _model is None:
        with _lock:
            if _model is None:
                from langchain_groq import ChatGroq

                _model = ChatGroq(
                    model=settings.groq_model,
                    temperature=settings.groq_temperature,
                    api_key=settings.groq_api_key,
                    timeout=settings.groq_timeout_seconds,
                    max_retries=0,  # retries are handled below, with backoff
                )
                logger.info("Chat model initialised", extra={"model": settings.groq_model})

    return _model


def _retry_after_seconds(error: Exception, attempt: int) -> float:
    """Prefer the wait the provider asked for; otherwise back off."""

    match = re.search(r"try again in ([\d.]+)s", str(error))

    if match:
        return float(match.group(1)) + 0.5

    # Exponential backoff with jitter, so concurrent callers do not all
    # retry in lockstep and re-trigger the same limit.
    return min(2**attempt, 30) + random.uniform(0, 1)


def _log_usage(response, elapsed_seconds: float) -> None:
    """Record tokens and latency for every model call.

    Nothing tracked spend before, which for an LLM product is the number
    that decides whether it can stay switched on. The request id already
    on every log line ties these back to one user's turn.
    """

    usage = {}

    try:
        metadata = getattr(response, "usage_metadata", None) or {}
        usage = {
            "input_tokens": metadata.get("input_tokens"),
            "output_tokens": metadata.get("output_tokens"),
            "total_tokens": metadata.get("total_tokens"),
        }
    except Exception:  # pragma: no cover - provider metadata is best-effort
        usage = {}

    logger.info(
        "Model call complete",
        extra={
            "model": settings.groq_model,
            "duration_ms": round(elapsed_seconds * 1000, 1),
            **{key: value for key, value in usage.items() if value is not None},
        },
    )


def safe_invoke(prompt, max_retries: int | None = None):
    """Invoke the model, retrying transient failures.

    Retries rate limits (the free tier has a tokens-per-minute cap) as
    well as connection and timeout errors, which previously failed the
    whole request on the first blip.
    """

    from groq import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

    retryable = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)

    attempts = max_retries if max_retries is not None else settings.groq_max_retries
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            started = time.perf_counter()
            response = get_model().invoke(prompt)

            _log_usage(response, time.perf_counter() - started)

            return response

        except retryable as error:
            last_error = error

            if attempt == attempts - 1:
                break

            wait = _retry_after_seconds(error, attempt)

            logger.warning(
                "Model call failed; retrying",
                extra={
                    "error_type": type(error).__name__,
                    "wait_seconds": round(wait, 1),
                    "attempt": attempt + 1,
                    "max_attempts": attempts,
                },
            )

            time.sleep(wait)

    logger.error(
        "Model unavailable after retries",
        extra={"attempts": attempts, "error_type": type(last_error).__name__},
    )

    raise LLMUnavailable(
        "The assistant is temporarily unavailable. Please try again in a moment."
    ) from last_error
