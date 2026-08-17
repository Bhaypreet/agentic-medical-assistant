"""Structured logging with a per-request correlation id.

Replaces the ad-hoc print() calls that used to carry every diagnostic in
this service. Two rules apply throughout the codebase:

  1. Never log report content, OCR output or model responses that contain
     patient data. Log identifiers and counts instead. The one exception
     is guarded by settings.debug_log_report_content, which the config
     refuses to enable in production.
  2. Every log line emitted while handling a request carries that
     request's id, so a single user's path through the system can be
     reconstructed from the log stream.
"""

import json
import logging
import sys
from contextvars import ContextVar

from app.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so a log aggregator can index the fields."""

    def format(self, record: logging.LogRecord) -> str:

        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value

        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Readable single-line output for local development."""

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return super().format(record)


def configure_logging() -> None:

    handler = logging.StreamHandler(sys.stdout)

    if settings.is_production:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            ConsoleFormatter(
                fmt="%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # These are chatty at INFO and say nothing we need.
    for noisy in ("httpx", "urllib3", "faiss", "fastembed"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
