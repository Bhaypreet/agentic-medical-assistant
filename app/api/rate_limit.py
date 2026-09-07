"""Request rate limiting.

Every /chat call spends money (at least one Groq completion, plus the
follow-up suggestion generation) and /transcribe hits Whisper. All of it
was previously unauthenticated and unmetered, so a trivial loop could
exhaust the API quota - and safe_invoke's retry-with-sleep behaviour then
converted the resulting rate limits into held server threads.

Sign-in and sign-up have no credential to meter by, so they fall back to
the caller's address. Establishing what that address actually is takes
some care: see client_address below.
"""

import hashlib

from fastapi import Request
from slowapi import Limiter

from app.api.security import is_known_api_key
from app.config import settings


def _hashed(value: str) -> str:
    """A stable, non-reversible id, so credentials never reach the
    limiter's storage or its log lines."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def client_address(request: Request) -> str:
    """The address the request ultimately came from.

    request.client.host is the socket peer. Behind a load balancer that is
    the balancer, so every visitor would share one bucket and the first
    handful of sign-ups per minute would lock out everyone else.

    X-Forwarded-For can say who the real caller is, but any client can put
    whatever it likes in it, and each proxy appends rather than replaces.
    So only the number of hops the operator has actually declared is
    trusted: with TRUSTED_PROXY_HOPS=n the caller is the n-th entry from
    the right, and anything a client prepended sits further left and is
    ignored. At the default of 0 the header is not read at all.
    """

    peer = request.client.host if request.client else "unknown"
    hops = settings.trusted_proxy_hops

    if hops <= 0:
        return peer

    forwarded = [
        part.strip()
        for part in request.headers.get("X-Forwarded-For", "").split(",")
        if part.strip()
    ]

    if not forwarded:
        return peer

    index = len(forwarded) - hops

    # Fewer entries than declared hops means the request did not arrive
    # through the expected chain; the left-most is the best available
    # guess and is no weaker than trusting the peer.
    return forwarded[index] if index >= 0 else forwarded[0]


def acting_for(request: Request) -> str | None:
    """The visitor a trusted service caller is making this request for.

    The Streamlit frontend is a server-side client: it opens its own
    connection to this API for every visitor it serves, so all of them
    share its address and its machine key. Without this header one person
    fumbling a sign-up form spends the whole deployment's quota.

    It is honoured only for a caller presenting a configured machine key,
    so an ordinary client cannot use it to mint itself fresh buckets.
    """

    if not is_known_api_key(request.headers.get("X-API-Key")):
        return None

    return request.headers.get("X-Client-Address", "").strip()[:64] or None


def rate_limit_key(request: Request) -> str:
    """Limit per signed-in user, else per visitor, else per address.

    Keying on the credential means one caller cannot multiply their quota
    by rotating source addresses.
    """

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() == "bearer" and token.strip():
        return "tok:" + _hashed(token.strip())

    api_key = request.headers.get("X-API-Key")

    if api_key:
        # A machine key is shared by everyone the frontend serves, so on
        # its own it identifies the caller but must not define the quota.
        bucket = "key:" + _hashed(api_key)
        visitor = acting_for(request)

        return f"{bucket}|ip:{visitor}" if visitor else bucket

    # Sign-in attempts arrive without a credential by definition, so the
    # address is the only thing left to limit them by.
    return "ip:" + client_address(request)


limiter = Limiter(key_func=rate_limit_key, headers_enabled=True)
