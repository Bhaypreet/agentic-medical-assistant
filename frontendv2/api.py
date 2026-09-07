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


def _visitor_address() -> str:
    """The browser's address, as best this process can tell.

    This is a server-side client: it opens its own connection to the API
    for every visitor it serves. Left to itself the API therefore sees a
    single address for the whole deployment and meters everyone together,
    so one person fumbling a sign-up form locks out the rest. Passing the
    visitor on lets the API give each of them their own allowance.
    """

    import streamlit as st

    try:
        context = st.context

        # Whatever fronts this app appends to X-Forwarded-For, so the
        # visitor is the left-most entry.
        forwarded = (context.headers.get("X-Forwarded-For") or "").split(",")

        if forwarded[0].strip():
            return forwarded[0].strip()

        return (context.ip_address or "").strip()
    except Exception:
        # Outside a script run there is no request to read; metering then
        # falls back to this process's address, which is the old behaviour.
        return ""


def _headers() -> dict:
    """Credentials for the backend.

    A signed-in user's bearer token takes precedence; the machine key is
    only a fallback for running the app as a service account.
    """

    import streamlit as st

    token = st.session_state.get("auth_token")

    if token:
        return {"Authorization": f"Bearer {token}"}

    if not API_KEY:
        return {}

    headers = {"X-API-Key": API_KEY}
    visitor = _visitor_address()

    # Only honoured by the API alongside a recognised machine key, so it
    # cannot be used by an ordinary client to escape its own limit.
    if visitor:
        headers["X-Client-Address"] = visitor

    return headers


def _timeout(read: float = READ_TIMEOUT) -> tuple:
    return (CONNECT_TIMEOUT, read)


def _rate_limited_message(response: requests.Response) -> str:
    """Tell the user how long to wait, when the server says so.

    "Wait a moment" gave no way to tell a two-second pause from a
    minute-long one, so the natural response was to keep clicking - which
    is what had spent the allowance in the first place.
    """

    try:
        seconds = int(float(response.headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        seconds = 0

    if seconds <= 0:
        return "Too many attempts just now. Wait a moment and try again."

    if seconds < 60:
        wait = f"{seconds} second{'s' if seconds != 1 else ''}"
    else:
        minutes = (seconds + 59) // 60
        wait = f"{minutes} minute{'s' if minutes != 1 else ''}"

    return f"Too many attempts just now. Try again in about {wait}."


def _handle(response: requests.Response):

    if response.status_code == 401:
        raise AuthRequired("Your session has expired. Please sign in again.")

    if response.status_code == 429:
        raise ApiError(_rate_limited_message(response))

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
