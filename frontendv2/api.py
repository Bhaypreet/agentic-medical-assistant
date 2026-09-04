"""HTTP client for the assistant API.

Every call previously omitted a timeout, so a hung backend held a
Streamlit worker open indefinitely. Timeouts are now explicit everywhere,
errors are turned into a message the user can act on, and the credential
travels on the X-API-Key header.
"""

import contextlib
import json
import time

import requests

from config import (
    API_KEY,
    CONNECT_TIMEOUT,
    FASTAPI_URL,
    JOB_POLL_INTERVAL,
    JOB_POLL_TIMEOUT,
    READ_TIMEOUT,
    UPLOAD_READ_TIMEOUT,
)


class ApiError(Exception):
    """A request failed in a way worth showing the user."""


class AuthRequired(ApiError):
    """The caller is not signed in, or the token is no longer valid."""


def _headers() -> dict:
    """Credentials for the backend.

    A signed-in user's bearer token takes precedence; the machine key is
    only a fallback for running the app as a service account.
    """

    import streamlit as st

    token = st.session_state.get("auth_token")

    if token:
        return {"Authorization": f"Bearer {token}"}

    return {"X-API-Key": API_KEY} if API_KEY else {}


def _timeout(read: float = READ_TIMEOUT) -> tuple:
    return (CONNECT_TIMEOUT, read)


def _handle(response: requests.Response):

    if response.status_code == 401:
        raise AuthRequired("Your session has expired. Please sign in again.")

    if response.status_code == 429:
        raise ApiError(
            "You're sending requests faster than the assistant can handle. Wait a moment."
        )

    if response.status_code == 413:
        raise ApiError("That file is too large to upload.")

    if response.status_code == 415:
        raise ApiError("That file type isn't supported. Upload a PDF, PNG or JPEG.")

    if not response.ok:
        detail = ""

        try:
            detail = response.json().get("detail", "")
        except ValueError:
            detail = ""

        raise ApiError(
            detail
            if isinstance(detail, str) and detail
            else "The assistant is unavailable right now."
        )

    return response


def _request(method: str, path: str, *, read_timeout: float = READ_TIMEOUT, **kwargs):

    try:
        response = requests.request(
            method,
            f"{FASTAPI_URL}{path}",
            headers=_headers(),
            timeout=_timeout(read_timeout),
            **kwargs,
        )
    except requests.Timeout as exc:
        raise ApiError("The assistant took too long to respond. Please try again.") from exc
    except requests.ConnectionError as exc:
        raise ApiError("Can't reach the assistant. Is the backend running?") from exc

    return _handle(response)


# ----------------------------------------------------------------- chat


def chat(query: str, session_id: str, location: str = "") -> dict:

    return _request(
        "POST",
        "/chat",
        json={"query": query, "session_id": session_id, "location": location},
    ).json()


def chat_stream(query: str, session_id: str, location: str = ""):
    """Yield (event, payload) pairs from the streaming chat endpoint.

    Falls back to the blocking endpoint when streaming is unavailable, so
    the UI keeps working against an older backend.
    """

    try:
        response = requests.post(
            f"{FASTAPI_URL}/chat/stream",
            json={"query": query, "session_id": session_id, "location": location},
            headers={**_headers(), "Accept": "text/event-stream"},
            timeout=_timeout(),
            stream=True,
        )
    except (requests.Timeout, requests.ConnectionError):
        yield "message", {"response": chat(query, session_id, location)["response"]}
        return

    if response.status_code == 404:
        result = chat(query, session_id, location)
        yield "message", {"response": result["response"]}
        yield "suggestions", {"suggestions": result.get("suggestions", [])}
        return

    _handle(response)

    event = None

    for raw in response.iter_lines(decode_unicode=True):
        if raw is None:
            continue

        line = raw.strip()

        if not line:
            event = None
            continue

        if line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            try:
                payload = json.loads(line[len("data:") :].strip())
            except ValueError:
                continue

            yield event or "message", payload


def get_history(session_id: str) -> list[dict]:
    return _request("GET", "/history", params={"session_id": session_id}).json()["messages"]


def list_sessions() -> list[dict]:
    return _request("GET", "/sessions").json()


def delete_session(session_id: str) -> None:
    _request("DELETE", f"/sessions/{session_id}")


# -------------------------------------------------------------- reports


def upload_report(file_bytes: bytes, filename: str, session_id: str) -> dict:
    """Submit a report. Returns the queued job."""

    return _request(
        "POST",
        "/upload-report",
        params={"session_id": session_id},
        files={"file": (filename, file_bytes)},
        read_timeout=UPLOAD_READ_TIMEOUT,
    ).json()


def get_report_status(job_id: str) -> dict:
    return _request("GET", f"/report-status/{job_id}").json()


def wait_for_report(job_id: str, on_progress=None) -> dict:
    """Poll a report job until it finishes.

    Report processing used to run inside the upload request, so the client
    waited on an open socket with no progress and any proxy in front cut
    it first.
    """

    deadline = time.monotonic() + JOB_POLL_TIMEOUT

    while time.monotonic() < deadline:
        job = get_report_status(job_id)

        if job["status"] == "succeeded":
            return job["result"] or {}

        if job["status"] == "failed":
            raise ApiError(job.get("error") or "The report could not be processed.")

        if on_progress:
            on_progress(job["status"])

        time.sleep(JOB_POLL_INTERVAL)

    raise ApiError("The report is taking unusually long. Check back in a few minutes.")


def download_report_pdf(session_id: str) -> bytes:
    return _request(
        "GET",
        "/download-report",
        params={"session_id": session_id},
        read_timeout=UPLOAD_READ_TIMEOUT,
    ).content


# ---------------------------------------------------------------- voice


def transcribe_voice(audio_bytes: bytes) -> str:
    return _request(
        "POST",
        "/transcribe",
        files={"file": ("recording.wav", audio_bytes, "audio/wav")},
    ).json()["text"]


# ----------------------------------------------------------------- auth


def register(username: str, password: str, display_name: str = "") -> dict:
    return _request(
        "POST",
        "/auth/register",
        json={"username": username, "password": password, "display_name": display_name},
    ).json()


def login(username: str, password: str) -> dict:
    """Exchange credentials for a bearer token.

    A 401 here means the credentials were wrong, not that a session
    expired, so it is reported as an ordinary ApiError.
    """

    try:
        response = requests.post(
            f"{FASTAPI_URL}/auth/login",
            json={"username": username, "password": password},
            timeout=_timeout(),
        )
    except requests.Timeout as exc:
        raise ApiError("The assistant took too long to respond. Please try again.") from exc
    except requests.ConnectionError as exc:
        raise ApiError("Can't reach the assistant. Is the backend running?") from exc

    if response.status_code == 401:
        raise ApiError("Incorrect username or password.")

    return _handle(response).json()


def logout() -> None:
    # The token is discarded locally regardless of the server's answer.
    with contextlib.suppress(ApiError):
        _request("POST", "/auth/logout")


def whoami() -> dict:
    return _request("GET", "/auth/me").json()


def change_password(current_password: str, new_password: str) -> None:
    _request(
        "POST",
        "/auth/change-password",
        json={"current_password": current_password, "new_password": new_password},
    )
