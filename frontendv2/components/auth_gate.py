"""Sign-in gate.

Nothing in the app renders until a token is held. The token lives in
st.session_state, which is per browser session and never written to disk,
so closing the tab ends the session on this side and the token expires on
the server's side regardless.
"""

import re

import streamlit as st

import api
from config import MIN_PASSWORD_LENGTH

# Mirrors app.auth.service.USERNAME_PATTERN. The server stays the authority;
# this only saves the patient a network round trip - and, when the backend
# is asleep on a free instance, a 30-60s wait - to learn their password is
# one character short.
_USERNAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")


def registration_problem(username: str, password: str, confirm: str) -> str | None:
    """What is wrong with a sign-up form, checked without calling the API."""

    if not username or not password:
        return "Choose a username and password."

    if not _USERNAME.match(username.strip().lower()):
        return (
            "Username must be 3-32 characters, start with a letter or number, "
            "and use only letters, numbers, dots, hyphens or underscores."
        )

    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."

    if not password.strip():
        return "Password cannot be only whitespace."

    if password != confirm:
        return "The two passwords do not match."

    return None


def current_user() -> dict | None:
    return st.session_state.get("auth_user")


def is_signed_in() -> bool:
    return bool(st.session_state.get("auth_token"))


def _store(result: dict) -> None:
    st.session_state.auth_token = result["access_token"]
    st.session_state.auth_user = {
        "username": result.get("username", ""),
        "display_name": result.get("display_name") or result.get("username", ""),
    }
    # Chat state belongs to whoever just signed in, not to the previous
    # occupant of this browser session.
    st.session_state.pop("chat_state", None)
    st.session_state.pop("current_chat", None)


def sign_out() -> None:
    api.logout()

    for key in ("auth_token", "auth_user", "chat_state", "current_chat"):
        st.session_state.pop(key, None)

    st.rerun()


def _sign_in_form() -> None:
    with st.form("sign_in", clear_on_submit=False):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")

        if st.form_submit_button("Sign in", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("Enter your username and password.")
                return

            try:
                _store(api.login(username, password))
            except api.ApiError as error:
                st.error(str(error))
            else:
                st.rerun()


def _register_form() -> None:
    with st.form("register", clear_on_submit=False):
        username = st.text_input(
            "Choose a username",
            help="3-32 characters: letters, numbers, dots, hyphens or underscores.",
            autocomplete="username",
        )
        password = st.text_input(
            "Choose a password",
            type="password",
            help=f"At least {MIN_PASSWORD_LENGTH} characters.",
            autocomplete="new-password",
        )
        confirm = st.text_input("Confirm password", type="password", autocomplete="new-password")

        if st.form_submit_button("Create account", use_container_width=True, type="primary"):
            problem = registration_problem(username, password, confirm)

            if problem:
                st.error(problem)
                return

            try:
                _store(api.register(username, password))
            except api.ApiError as error:
                st.error(str(error))
            else:
                st.rerun()


def require_sign_in() -> bool:
    """Render the gate. Returns True when the app may proceed."""

    if is_signed_in():
        return True

    # Once per browser session: wake the API while the form is being filled.
    if not st.session_state.get("_backend_woken"):
        st.session_state["_backend_woken"] = True
        api.wake_backend()

    st.markdown(
        """
        <div class="app-header">
            <h1>🩺 Agentic Medical Assistant</h1>
            <p>Sign in to analyse lab reports, check symptoms and find nearby care</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, middle, _ = st.columns([1, 2, 1])

    with middle:
        sign_in_tab, register_tab = st.tabs(["Sign in", "Create account"])

        with sign_in_tab:
            _sign_in_form()

        with register_tab:
            _register_form()

        st.caption(
            "Your reports and conversations are private to your account. "
            "This app provides information only and is not a medical diagnosis."
        )

    return False
