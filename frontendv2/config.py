import os

# Use local backend for local testing; switch to the live Render URL only
# when actually deploying (or set FASTAPI_URL as an environment variable)
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://127.0.0.1:8000")

APP_NAME = "🩺 Agentic Medical Assistant"

DEFAULT_CHAT_NAME = "New Chat"