import streamlit as st


def render_messages(messages) -> None:
    """Render the conversation as returned by the backend."""

    for message in messages or []:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
