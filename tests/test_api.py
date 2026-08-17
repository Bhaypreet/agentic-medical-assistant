import io
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.config import settings

MINIMAL_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture
def client():
    # raise_server_exceptions=False so the app's own 500 handler runs,
    # which is the behaviour under test.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def keyed(monkeypatch):
    """Run with authentication switched on."""
    monkeypatch.setattr(settings, "api_keys", "alice-key,bob-key")
    return {"alice": {"X-API-Key": "alice-key"}, "bob": {"X-API-Key": "bob-key"}}


def _answer(text="Drink fluids and rest."):
    return {"response": text, "severity": 1, "emergency": False}


# --------------------------------------------------------------- meta


def test_health_is_liveness_only(client):
    assert client.get("/health").json() == {"status": "alive"}


def test_readiness_reports_individual_checks(client):
    body = client.get("/ready").json()

    # /health used to return a hardcoded "healthy" while the vector store
    # was missing and the credential invalid.
    assert "database" in body["checks"]
    assert "credentials" in body["checks"]
    assert "knowledge_base" in body["checks"]


def test_every_response_carries_a_correlation_id(client):
    assert client.get("/health").headers["X-Request-ID"]


# --------------------------------------------------------------- auth


def test_requests_without_a_key_are_rejected_when_keys_are_configured(client, keyed):
    response = client.post("/chat", json={"query": "hi", "session_id": str(uuid.uuid4())})
    assert response.status_code == 401


def test_requests_with_an_unknown_key_are_rejected(client, keyed):
    response = client.post(
        "/chat",
        json={"query": "hi", "session_id": str(uuid.uuid4())},
        headers={"X-API-Key": "not-a-real-key"},
    )
    assert response.status_code == 401


def test_a_valid_key_is_accepted(client, keyed):
    with (
        patch("app.api.routes.graph.invoke", return_value=_answer()),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        response = client.post(
            "/chat",
            json={"query": "I feel fine", "session_id": str(uuid.uuid4())},
            headers=keyed["alice"],
        )

    assert response.status_code == 200


# --------------------------------------------------------------- IDOR


def test_one_caller_cannot_read_another_callers_chat(client, keyed):
    """The original vulnerability: session_id came from the request and
    was trusted, so guessing a UUID exposed someone's medical data."""

    session_id = str(uuid.uuid4())

    with (
        patch("app.api.routes.graph.invoke", return_value=_answer("Your haemoglobin is low.")),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        client.post(
            "/chat",
            json={"query": "explain my report", "session_id": session_id},
            headers=keyed["alice"],
        )

    alice = client.get(f"/history?session_id={session_id}", headers=keyed["alice"]).json()
    assert len(alice["messages"]) == 2

    bob = client.get(f"/history?session_id={session_id}", headers=keyed["bob"]).json()
    assert bob["messages"] == []


def test_one_caller_cannot_download_another_callers_report(client, keyed):
    session_id = str(uuid.uuid4())

    from app.api.security import principal_for_key
    from app.session.session_manager import session_manager

    session_manager.save_report_data(
        session_id,
        [{"report_type": "CBC", "parameters": {}}],
        "Summary",
        owner=principal_for_key("alice-key"),
    )

    assert (
        client.get(f"/download-report?session_id={session_id}", headers=keyed["alice"]).status_code
        == 200
    )
    assert (
        client.get(f"/download-report?session_id={session_id}", headers=keyed["bob"]).status_code
        == 404
    )


def test_sessions_are_listed_per_caller(client, keyed):
    session_id = str(uuid.uuid4())

    with (
        patch("app.api.routes.graph.invoke", return_value=_answer()),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        client.post(
            "/chat", json={"query": "hello", "session_id": session_id}, headers=keyed["alice"]
        )

    alice_ids = {s["id"] for s in client.get("/sessions", headers=keyed["alice"]).json()}
    bob_ids = {s["id"] for s in client.get("/sessions", headers=keyed["bob"]).json()}

    assert session_id in alice_ids
    assert session_id not in bob_ids


# ------------------------------------------------------------ validation


@pytest.mark.parametrize("session_id", ["../../etc/passwd", "a b", "x" * 65, ""])
def test_malformed_session_ids_are_rejected(client, session_id):
    response = client.post("/chat", json={"query": "hi", "session_id": session_id})
    assert response.status_code in (400, 422)


def test_empty_query_is_rejected(client):
    response = client.post("/chat", json={"query": "", "session_id": str(uuid.uuid4())})
    assert response.status_code == 422


# --------------------------------------------------------------- upload


def test_upload_rejects_a_disallowed_extension(client):
    response = client.post(
        f"/upload-report?session_id={uuid.uuid4()}",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
    )
    assert response.status_code == 415


def test_upload_rejects_contents_that_do_not_match_the_extension(client):
    response = client.post(
        f"/upload-report?session_id={uuid.uuid4()}",
        files={"file": ("notreally.pdf", b"this is plain text", "application/pdf")},
    )
    assert response.status_code == 415


def test_upload_rejects_an_oversized_file(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_bytes", 64)

    response = client.post(
        f"/upload-report?session_id={uuid.uuid4()}",
        files={"file": ("big.pdf", MINIMAL_PDF + b"0" * 5000, "application/pdf")},
    )
    assert response.status_code == 413


def test_upload_rejects_an_empty_file(client):
    response = client.post(
        f"/upload-report?session_id={uuid.uuid4()}",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code in (400, 415)


def test_a_traversal_filename_never_reaches_the_filesystem(client, tmp_path, monkeypatch):
    """filename="../../app/api/routes.py" used to be joined into the
    destination path verbatim and overwrote application source."""

    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")

    with patch("app.api.routes.report_jobs.submit", return_value="job-1"):
        response = client.post(
            f"/upload-report?session_id={uuid.uuid4()}",
            files={"file": ("../../pwned.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    assert not (tmp_path / "pwned.pdf").exists()

    written = list((tmp_path / "uploads").iterdir())
    assert len(written) == 1
    assert written[0].name.endswith(".pdf")
    uuid.UUID(written[0].stem)  # server-generated name


def test_upload_returns_a_job_id_rather_than_blocking(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")

    with patch("app.api.routes.report_jobs.submit", return_value="job-42") as submit:
        response = client.post(
            f"/upload-report?session_id={uuid.uuid4()}",
            files={"file": ("labs.pdf", MINIMAL_PDF, "application/pdf")},
        )

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-42"
    assert submit.called


def test_report_status_for_an_unknown_job_is_not_found(client):
    assert client.get(f"/report-status/{uuid.uuid4()}").status_code == 404


# ------------------------------------------------------------- reports


def test_download_without_an_analysed_report_is_not_found(client):
    assert client.get(f"/download-report?session_id={uuid.uuid4()}").status_code == 404


def test_deleting_a_session_also_removes_its_vector_store(client):
    from app.session.session_manager import session_manager

    session_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())

    session_manager.save_report(session_id, report_id)

    with patch("app.api.routes.delete_report_store") as delete_store:
        assert client.delete(f"/sessions/{session_id}").status_code == 204

    # Deleting a chat used to orphan its vector store on disk forever.
    delete_store.assert_called_once_with(report_id)


# ---------------------------------------------------------------- chat


def test_chat_appends_a_disclaimer(client):
    with (
        patch("app.api.routes.graph.invoke", return_value=_answer("Rest and fluids.")),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        body = client.post(
            "/chat", json={"query": "I have a cold", "session_id": str(uuid.uuid4())}
        ).json()

    assert "does not replace advice" in body["response"]


def test_an_emergency_result_leads_with_escalation(client):
    graph_result = {
        "response": "## Assessment\n\n**Risk level:** Emergency",
        "severity": 5,
        "emergency": True,
    }

    with (
        patch("app.api.routes.graph.invoke", return_value=graph_result),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        body = client.post(
            "/chat",
            json={"query": "crushing chest pain", "session_id": str(uuid.uuid4())},
        ).json()

    # "Emergency: True" used to be rendered as a bare field with no
    # instruction to call anyone.
    assert body["response"].startswith("## ⚠️ Seek emergency care now")
    assert "112" in body["response"]


def test_chat_history_is_persisted_server_side(client):
    session_id = str(uuid.uuid4())

    with (
        patch("app.api.routes.graph.invoke", return_value=_answer("Answer one.")),
        patch("app.api.routes.generate_suggestions", return_value=[]),
    ):
        client.post("/chat", json={"query": "question one", "session_id": session_id})

    messages = client.get(f"/history?session_id={session_id}").json()["messages"]

    assert messages[0] == {"role": "user", "content": "question one"}
    assert "Answer one." in messages[1]["content"]


def test_an_unhandled_error_does_not_leak_internals(client):
    with patch("app.api.routes.graph.invoke", side_effect=RuntimeError("secret db password")):
        response = client.post("/chat", json={"query": "hello", "session_id": str(uuid.uuid4())})

    assert response.status_code == 500
    assert "secret db password" not in response.text


# --------------------------------------------------------------- voice


def test_transcribe_rejects_an_empty_recording(client):
    response = client.post(
        "/transcribe", files={"file": ("clip.wav", io.BytesIO(b""), "audio/wav")}
    )
    assert response.status_code == 400


def test_rate_limiting_rejects_a_burst(client):
    """Unmetered endpoints that each spend a model call were a trivial
    way to exhaust the API quota."""

    from app.api.rate_limit import limiter

    limiter.enabled = True

    try:
        with (
            patch("app.api.routes.graph.invoke", return_value=_answer()),
            patch("app.api.routes.generate_suggestions", return_value=[]),
        ):
            codes = [
                client.post(
                    "/chat", json={"query": "hello", "session_id": str(uuid.uuid4())}
                ).status_code
                for _ in range(25)
            ]
    finally:
        limiter.enabled = False

    assert 429 in codes
