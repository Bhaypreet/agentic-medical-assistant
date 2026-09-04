"""Authentication and request-scoping.

Originally every route took a `session_id` straight from the request and
trusted it, so anyone who guessed a UUID could read another person's
report analysis, chat history and downloadable PDF.

Two credentials are accepted now:

  * A bearer token from signing in with a username and password. This is
    how people use the app, and the owner is that account - so two people
    using the same deployment cannot see each other's data.
  * An X-API-Key from the configured machine keys, for service-to-service
    callers. The owner is a hash of the key.

There is no anonymous access to any data endpoint, in any environment.
The previous build disabled authentication whenever API_KEYS happened to
be unset, which meant a deployment could be wide open by omission.
"""

import hashlib
import hmac
import re
import uuid

from fastapi import Depends, Header, HTTPException, status

from app.auth.service import Principal, principal_for_token
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Sign in to continue.",
    headers={"WWW-Authenticate": "Bearer"},
)


def principal_for_key(api_key: str) -> str:
    """A stable, non-reversible identifier for a machine credential."""

    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"key:{digest[:32]}"


def _machine_principal(x_api_key: str | None) -> Principal | None:
    allowed = settings.allowed_api_keys

    if not x_api_key or not allowed:
        return None

    # Every candidate is compared so a timing difference cannot be used
    # to recover a key byte by byte.
    matched = False
    for candidate in allowed:
        if hmac.compare_digest(x_api_key, candidate):
            matched = True

    if not matched:
        logger.warning("Rejected request with an unrecognised API key")
        return None

    return Principal(owner=principal_for_key(x_api_key), user_id=None, username="service")


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        return ""

    scheme, _, token = authorization.partition(" ")

    return token.strip() if scheme.lower() == "bearer" else ""


def require_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> Principal:
    """Resolve the caller, or reject the request."""

    token = _bearer_token(authorization)

    if token:
        principal = principal_for_token(token)

        if principal is not None:
            return principal

        # An expired or revoked token is not a server error - the client
        # should sign in again.
        raise UNAUTHENTICATED

    machine = _machine_principal(x_api_key)

    if machine is not None:
        return machine

    raise UNAUTHENTICATED


def require_owner(principal: Principal = Depends(require_principal)) -> str:
    """The owner string every session read and write is scoped by."""

    return principal.owner


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
