"""Speech-to-text via Groq's Whisper endpoint."""

import threading

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_client = None


def _get_client():
    """Build the client on first use rather than at import."""

    global _client

    if _client is None:
        with _lock:
            if _client is None:
                from groq import Groq

                _client = Groq(
                    api_key=settings.groq_api_key,
                    timeout=settings.groq_timeout_seconds,
                )

    return _client


def transcribe_audio(audio_path: str) -> str:

    with open(audio_path, "rb") as handle:
        transcription = _get_client().audio.transcriptions.create(
            file=(audio_path, handle.read()),
            model=settings.groq_transcription_model,
        )

    text = transcription.text or ""

    logger.info("Transcribed audio", extra={"characters": len(text)})

    return text
