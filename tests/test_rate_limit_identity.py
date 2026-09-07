"""Who a rate limit counts against.

Limits are useless if they meter everyone as one caller, and worse than
useless if a caller can pick their own bucket. Both were possible: the
API took the socket peer as the client, so every visitor behind a proxy
or behind the Streamlit frontend shared one allowance, and a handful of
sign-ups locked out the rest.
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.rate_limit import client_address, rate_limit_key
from app.config import settings


class FakeRequest:
    """Just the parts of starlette's Request the key function reads."""

    def __init__(self, headers=None, peer="10.0.0.1"):
        self.headers = headers or {}
        self.client = type("Client", (), {"host": peer})() if peer else None


# ----------------------------------------------------------- proxy hops


def test_peer_is_the_client_when_nothing_is_proxying():
    with patch.object(settings, "trusted_proxy_hops", 0):
        request = FakeRequest({"X-Forwarded-For": "9.9.9.9"}, peer="10.0.0.1")

        # The header is not read at all: with no proxy to vouch for it,
        # anyone could send it.
        assert client_address(request) == "10.0.0.1"


def test_one_declared_hop_reads_through_the_balancer():
    with patch.object(settings, "trusted_proxy_hops", 1):
        request = FakeRequest({"X-Forwarded-For": "203.0.113.7"}, peer="10.0.0.1")

        assert client_address(request) == "203.0.113.7"


def test_a_client_cannot_forge_a_bucket_by_prepending():
    """The proxy appends, so anything the client sent sits to the left."""

    with patch.object(settings, "trusted_proxy_hops", 1):
        forged = FakeRequest({"X-Forwarded-For": "1.2.3.4, 203.0.113.7"}, peer="10.0.0.1")

        assert client_address(forged) == "203.0.113.7"

        # ...and each forgery attempt lands in the same bucket as the
        # caller's honest one, so it buys nothing.
        honest = FakeRequest({"X-Forwarded-For": "203.0.113.7"}, peer="10.0.0.1")
        assert rate_limit_key(forged) == rate_limit_key(honest)


def test_two_declared_hops_step_back_two():
    with patch.object(settings, "trusted_proxy_hops", 2):
        request = FakeRequest({"X-Forwarded-For": "203.0.113.7, 10.1.1.1"}, peer="10.0.0.1")

        assert client_address(request) == "203.0.113.7"


def test_missing_header_falls_back_to_the_peer():
    with patch.object(settings, "trusted_proxy_hops", 1):
        assert client_address(FakeRequest({}, peer="10.0.0.1")) == "10.0.0.1"


# ------------------------------------------------- visitors of a service


def test_visitors_of_one_service_caller_are_metered_separately():
    """The frontend holds one key for everybody it serves."""

    with patch.object(settings, "api_keys", "service-key"):
        first = FakeRequest({"X-API-Key": "service-key", "X-Client-Address": "1.1.1.1"})
        second = FakeRequest({"X-API-Key": "service-key", "X-Client-Address": "2.2.2.2"})

        assert rate_limit_key(first) != rate_limit_key(second)


def test_a_forwarded_visitor_is_ignored_without_a_recognised_key():
    """Otherwise the header would be a way for anyone to reset their own
    limit at will."""

    with patch.object(settings, "api_keys", "service-key"):
        first = FakeRequest({"X-API-Key": "wrong-key", "X-Client-Address": "1.1.1.1"})
        second = FakeRequest({"X-API-Key": "wrong-key", "X-Client-Address": "2.2.2.2"})

        assert rate_limit_key(first) == rate_limit_key(second)


def test_signed_in_users_are_metered_per_account():
    first = FakeRequest({"Authorization": "Bearer token-one"})
    second = FakeRequest({"Authorization": "Bearer token-two"})

    assert rate_limit_key(first) != rate_limit_key(second)
    assert "token-one" not in rate_limit_key(first)


# ------------------------------------------------------ end to end


@pytest.fixture
def limited():
    from app.api.rate_limit import limiter

    limiter.enabled = True
    limiter.reset()
    try:
        yield
    finally:
        limiter.enabled = False
        limiter.reset()


def _register(test_client, **headers):
    return test_client.post(
        "/auth/register",
        json={
            "username": f"u{uuid.uuid4().hex[:12]}",
            "password": "correct horse battery",
        },
        headers=headers,
    )


def test_one_visitor_exhausting_signups_does_not_lock_out_another(limited):
    """The reported failure: creating an account returned 429 because
    somebody else's attempts had already spent the shared allowance."""

    with (
        TestClient(app) as client,
        patch.object(settings, "api_keys", "service-key"),
    ):
        base = {"X-API-Key": "service-key"}

        spent = [
            _register(client, **base, **{"X-Client-Address": "1.1.1.1"}).status_code
            for _ in range(14)
        ]

        assert 429 in spent, "the noisy visitor should hit their own limit"

        # A different visitor arriving through the same frontend is
        # unaffected.
        other = _register(client, **base, **{"X-Client-Address": "2.2.2.2"})

        assert other.status_code == 201, other.text


def test_the_429_says_how_long_to_wait(limited):
    with TestClient(app) as client:
        last = None

        for _ in range(14):
            last = _register(client)

        assert last.status_code == 429
        assert int(last.headers["Retry-After"]) >= 0
