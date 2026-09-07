import os

import streamlit as st


def _setting(name: str, default: str = "") -> str:
    """Read configuration from Streamlit secrets, then the environment.

    Streamlit Community Cloud supplies configuration through st.secrets
    rather than environment variables, so reading only os.getenv left
    FASTAPI_URL on its localhost default and every API call failed with
    "Can't reach the assistant". Accessing st.secrets raises when no
    secrets file exists, which is the normal case when running locally.
    """

    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    return os.getenv(name, default)


def _normalise_url(value: str) -> str:
    """Accept a bare host as well as a full URL.

    Platform service discovery hands out a hostname with no scheme -
    Render's `fromService` blueprint reference yields "api.onrender.com".
    requests rejects that with MissingSchema, so every call would fail on
    an otherwise correctly wired deploy. Assume TLS, except for the local
    addresses that will not have it.
    """

    value = value.strip().rstrip("/")

    if not value or "://" in value:
        return value

    host = value.split("/", 1)[0].split(":", 1)[0]
    local = host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

    return f"{'http' if local else 'https'}://{value}"


FASTAPI_URL = _normalise_url(_setting("FASTAPI_URL", "http://127.0.0.1:8000"))

# Sent as X-API-Key. Required whenever the backend has API_KEYS configured.
API_KEY = _setting("MEDICAL_ASSISTANT_API_KEY", "")

APP_NAME = "🩺 Agentic Medical Assistant"

DEFAULT_CHAT_NAME = "New Chat"

# Connect and read timeouts, in seconds. Every call previously omitted a
# timeout entirely, so a hung backend held a Streamlit worker forever.
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 60
UPLOAD_READ_TIMEOUT = 120

# How long to keep polling a report job before giving up.
JOB_POLL_INTERVAL = 2
JOB_POLL_TIMEOUT = 600
