import os

FASTAPI_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000").rstrip("/")

# Sent as X-API-Key. Required whenever the backend has API_KEYS configured.
API_KEY = os.getenv("MEDICAL_ASSISTANT_API_KEY", "")

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
