import streamlit as st


def render_messages(chat):

    messages = chat.get("messages", [])

    for message in messages:

        with st.chat_message(message["role"]):

            st.markdown(message["content"])


def add_message(chat, role, content):

    if "messages" not in chat:
        chat["messages"] = []

    chat["messages"].append(
        {
            "role": role,
            "content": content
        }
    )