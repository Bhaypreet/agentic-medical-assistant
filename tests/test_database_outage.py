"""The API survives a database it cannot reach.

init_db() used to raise during startup, which made uvicorn abort, gunicorn
exit with status 3 and the platform restart the container into the same
failure. Now the process stays up, data endpoints answer 503, and the
connection is retried until the database comes back.
"""

import time
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import main, routes
from app.config import settings


def _unreachable():
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_startup_survives_an_unreachable_database_and_recovers(monkeypatch):
    monkeypatch.setattr(settings, "database_retry_interval_seconds", 0.01)

    calls = {"count": 0}

    def flaky_init(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise _unreachable()

    with (
        patch.object(main, "init_db_with_retry", side_effect=flaky_init),
        TestClient(main.app, raise_server_exceptions=False) as client,
    ):
        # Liveness answers even before the database does.
        assert client.get("/health").status_code == 200

        deadline = time.monotonic() + 5
        while not main.app.state.database_ready and time.monotonic() < deadline:
            time.sleep(0.01)

        assert main.app.state.database_ready is True

    assert calls["count"] == 3


def test_database_errors_answer_503_not_500():
    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post(
            "/auth/register",
            json={"username": f"user{uuid.uuid4().hex[:10]}", "password": "correct horse battery"},
        )
        client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

        with patch.object(routes.session_manager, "list_sessions", side_effect=_unreachable()):
            response = client.get("/sessions")

    assert response.status_code == 503
    assert "request_id" in response.json()
