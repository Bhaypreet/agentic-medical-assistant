"""Authentication and request-scoping.

Previously every route took a `session_id` straight from the request and
trusted it, so anyone who guessed a UUID could read another person's
report analysis, chat history and downloadable PDF.

Two things fix that:

  * The caller's identity ("owner") is derived from a credential, never
    from the request body. It is a hash of the presented API key, so the
    key itself is never stored or logged.
  * The session id remains a client-chosen conversation key, but it is
    namespaced by owner in the database, so it addresses only that
    owner's data.
"""

import hashlib
import hmac
import re
import uuid

from fastapi import Depends, Header, HTTPException, status

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

ANONYMOUS = "anonymous"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def principal_for_key(api_key: str) -> str:
    """A stable, non-reversible identifier for a credential."""

    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"key:{digest[:32]}"


def require_owner(x_api_key: str | None = Header(default=None)) -> str:
    """Resolve the calling principal, or reject the request.

    With no API_KEYS configured the service runs unauthenticated, which is
    only permitted outside production - app.config refuses to start a
    production environment without keys.
    """

    allowed = settings.allowed_api_keys

    if not allowed:
        if settings.is_production:  # pragma: no cover - config forbids this
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server is misconfigured.",
            )
        return ANONYMOUS

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Compare against every configured key in constant time, so a timing
    # difference cannot be used to recover a key byte by byte.
    matched = False
    for candidate in allowed:
        if hmac.compare_digest(x_api_key, candidate):
            matched = True

    if not matched:
        logger.warning("Rejected request with an unrecognised API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return principal_for_key(x_api_key)


def validate_session_id(session_id: str) -> str:
    """Reject session ids that could escape their namespace.

    Session ids reach filesystem paths and log lines, so they are held to
    a conservative character set.
    """

    if not session_id or not _SAFE_ID.match(session_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id must be 1-64 characters of A-Z, a-z, 0-9, '-' or '_'.",
        )

    return session_id


def validate_report_id(report_id: str) -> str:
    """Report ids are joined into filesystem paths, so they must be UUIDs.

    Without this a tampered session record could point the FAISS loader -
    which unpickles - at any path on disk.
    """

    try:
        return str(uuid.UUID(str(report_id)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"Invalid report id: {report_id!r}") from exc


OwnerDep = Depends(require_owner)
