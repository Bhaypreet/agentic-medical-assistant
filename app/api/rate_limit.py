"""Request rate limiting.

Every /chat call spends money (at least one Groq completion, plus the
follow-up suggestion generation) and /transcribe hits Whisper. All of it
was previously unauthenticated and unmetered, so a trivial loop could
exhaust the API quota - and safe_invoke's retry-with-sleep behaviour then
converted the resulting rate limits into held server threads.
"""

import hashlib

from fastapi import Request
from slowapi import Limiter


def rate_limit_key(request: Request) -> str:
    """Limit per credential where one is presented, per client IP otherwise.

    Keying on the credential means one caller cannot multiply their quota
    by rotating source addresses. The credential is hashed rather than
    used directly, so it never reaches the limiter's storage or logs.
    """

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")

    if scheme.lower() == "bearer" and token.strip():
        return "tok:" + hashlib.sha256(token.strip().encode("utf-8")).hexdigest()[:32]

    api_key = request.headers.get("X-API-Key")

    if api_key:
        return "key:" + hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:32]

    client = request.client

    # Sign-in attempts arrive without a credential by definition, so the
    # address is the only thing left to limit them by.
    return f"ip:{client.host}" if client else "ip:unknown"


limiter = Limiter(key_func=rate_limit_key, headers_enabled=True)
