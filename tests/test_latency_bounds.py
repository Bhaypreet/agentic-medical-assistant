"""Time bounds on the slow paths.

A turn could run for minutes: every model call - including the optional
follow-up suggestions - went through 4 attempts at up to 60s each plus
backoff, while the frontend gave up after 60s. And the UI streams through
/chat/stream, which never named the chat.
"""

import sys
import time
import types
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.llm import model
from app.tools import suggestion_generator

# ----------------------------------------------------------- model budget


class _RateLimited(Exception):
    pass


class _Other(Exception):
    pass


def _fake_groq():
    """safe_invoke imports its retryable errors from groq at call time, and
    groq is not installed in the test environment (CI skips it too)."""

    fake = types.ModuleType("groq")
    fake.RateLimitError = _RateLimited
    fake.APIConnectionError = fake.APITimeoutError = fake.InternalServerError = _Other
    return patch.dict(sys.modules, {"groq": fake})


def test_a_retry_that_cannot_finish_in_budget_is_not_attempted():
    client = MagicMock()
    client.invoke.side_effect = _RateLimited("rate limited, try again in 30s")

    with (
        _fake_groq(),
        patch.object(model, "get_model", return_value=client),
        patch.object(model.time, "sleep") as sleep,
        pytest.raises(model.LLMUnavailable),
    ):
        model.safe_invoke("hi", max_retries=4, budget_seconds=10)

    # The provider asked for 30s, which cannot fit in a 10s budget.
    sleep.assert_not_called()
    assert client.invoke.call_count == 1


def test_a_retry_that_fits_is_still_attempted():
    client = MagicMock()
    client.invoke.side_effect = [_RateLimited("try again in 1s"), MagicMock(content="ok")]

    with (
        _fake_groq(),
        patch.object(model, "get_model", return_value=client),
        patch.object(model, "_log_usage"),
        patch.object(model.time, "sleep"),
    ):
        assert model.safe_invoke("hi", max_retries=3, budget_seconds=30).content == "ok"

    assert client.invoke.call_count == 2


def test_default_budget_fits_inside_the_frontend_timeout():
    assert settings.groq_call_budget_seconds < 60
    assert settings.groq_timeout_seconds < settings.groq_call_budget_seconds


# ----------------------------------------------------------- suggestions


def test_slow_suggestions_are_dropped_not_waited_for():
    def slow(*_args, **_kwargs):
        time.sleep(3)
        return MagicMock(content="a\nb\nc")

    with (
        patch.object(suggestion_generator, "safe_invoke", side_effect=slow),
        patch.object(suggestion_generator, "SUGGESTION_BUDGET_SECONDS", 0.5),
    ):
        started = time.monotonic()
        result = suggestion_generator.generate_suggestions("q", "a")
        elapsed = time.monotonic() - started

    assert result == []
    assert elapsed < 2


def test_suggestions_get_one_short_attempt():
    with patch.object(
        suggestion_generator, "safe_invoke", return_value=MagicMock(content="one\ntwo\nthree")
    ) as invoke:
        assert suggestion_generator.generate_suggestions("q", "a") == ["one", "two", "three"]

    _, kwargs = invoke.call_args
    assert kwargs["max_retries"] == 1
    assert kwargs["budget_seconds"] <= 10


# ------------------------------------------------ naming via the stream


def test_the_streaming_endpoint_names_the_chat():
    """The UI uses /chat/stream; naming only /chat left every chat unnamed."""

    from app.api.main import app

    with TestClient(app) as client:
        username = "s" + uuid.uuid4().hex[:10]
        token = client.post(
            "/auth/register", json={"username": username, "password": "correct horse battery"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        sid = str(uuid.uuid4())

        with (
            patch(
                "app.api.routes.graph.stream", return_value=iter([{"rag_node": {"response": "ok"}}])
            ),
            patch("app.api.routes.graph.invoke", return_value={"response": "ok"}),
            patch("app.api.routes.generate_suggestions", return_value=[]),
        ):
            client.post(
                "/chat/stream",
                headers=headers,
                json={"query": "Why do I feel dizzy when standing up?", "session_id": sid},
            )

        names = [s["chat_name"] for s in client.get("/sessions", headers=headers).json()]

    assert "Why do I feel dizzy when standing up" in names
