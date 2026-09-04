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


FASTAPI_URL = _setting("FASTAPI_URL", "http://127.0.0.1:8000").rstrip("/")

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
