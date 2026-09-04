"""Request rate limiting.

Every /chat call spends money (at least one Groq completion, plus the
follow-up suggestion generation) and /transcribe hits Whisper. All of it
was previously unauthenticated and unmetered, so a trivial loop could
exhaust the API quota - and safe_invoke's retry-with-sleep behaviour then
converted the resulting rate limits into held server threads.
"""

from fastapi import Request
from slowapi import Limiter

from app.api.security import ANONYMOUS, principal_for_key


def rate_limit_key(request: Request) -> str:
    """Limit per credential where one is presented, per client IP otherwise.

    Keying on the credential means one caller cannot multiply their quota
    by rotating source addresses.
    """

    api_key = request.headers.get("X-API-Key")

    if api_key:
        return principal_for_key(api_key)

    client = request.client

    return f"ip:{client.host}" if client else ANONYMOUS


limiter = Limiter(key_func=rate_limit_key, headers_enabled=True)
