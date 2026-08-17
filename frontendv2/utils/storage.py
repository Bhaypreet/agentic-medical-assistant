"""Local, per-browser chat state.

Chats used to be written to one server-side folder that every visitor
read, so on a deployed instance anyone could see everyone else's chats,
uploaded report names and health summaries - no attack required.

Nothing about a conversation is persisted on the frontend now. Chat ids
live in st.session_state, which is per browser session, and the messages
themselves come from the backend, which scopes them to the credential.
"""

import contextlib
import uuid

import streamlit as st

import api

DEFAULT_CHAT_NAME = "New Chat"


def _local() -> dict:
    """Per-browser view state, keyed by chat id."""

    if "chat_state" not in st.session_state:
        st.session_state.chat_state = {}

    return st.session_state.chat_state


def create_chat() -> dict:

    chat = {
        "id": str(uuid.uuid4()),
        "chat_name": DEFAULT_CHAT_NAME,
        "report": None,
        "summary": "",
        "suggestions": [],
        "uploaded_file": "",
    }

    _local()[chat["id"]] = chat

    return chat


def save_chat(chat: dict) -> None:
    """Keep view state for this browser session. Messages are not stored
    here - the backend is the single source of truth for those."""

    _local()[chat["id"]] = chat


def get_chat(chat_id: str) -> dict | None:
    return _local().get(chat_id)


def load_messages(chat_id: str) -> list[dict]:
    """The conversation, from the server."""

    try:
        return api.get_history(chat_id)
    except api.ApiError:
        return []


@st.cache_data(ttl=10, show_spinner=False)
def _fetch_sessions() -> list[dict]:
    """Cached so the sidebar does not re-fetch on every widget interaction.

    The previous implementation read and parsed every chat file from disk
    on every Streamlit rerun, which happens on each interaction.
    """

    try:
        return api.list_sessions()
    except api.ApiError:
        return []


def load_all_chats() -> list[dict]:
    """Chat summaries for this credential, most recently updated first."""

    remote = _fetch_sessions()
    local = _local()

    merged = []

    for summary in remote:
        cached = local.get(summary["id"], {})
        merged.append(
            {
                "id": summary["id"],
                "chat_name": summary.get("chat_name") or DEFAULT_CHAT_NAME,
                "has_report": summary.get("has_report", False),
                "updated_at": summary.get("updated_at"),
                "report": cached.get("report"),
                "summary": cached.get("summary", ""),
                "suggestions": cached.get("suggestions", []),
                "uploaded_file": cached.get("uploaded_file", ""),
            }
        )

    seen = {item["id"] for item in merged}

    # Chats created in this browser that have no messages yet are not
    # known to the server, so they would otherwise disappear.
    merged.extend(chat for chat_id, chat in local.items() if chat_id not in seen)

    return merged


def refresh_sessions() -> None:
    _fetch_sessions.clear()


def delete_chat(chat_id: str) -> None:

    with contextlib.suppress(api.ApiError):
        api.delete_session(chat_id)

    _local().pop(chat_id, None)
    refresh_sessions()
