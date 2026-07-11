import streamlit as st

from utils.storage import (
    load_all_chats,
    delete_chat,
    create_chat
)


def render_sidebar():

    with st.sidebar:

        st.title("🩺 Medical Assistant")
        st.markdown("---")

        if st.button("➕ New Chat", use_container_width=True):
            session = create_chat()
            st.session_state.current_chat = session
            st.rerun()

        st.markdown("---")
        st.subheader("💬 Chats")

        chats = load_all_chats()
        chats.sort(key=lambda x: x["chat_name"])

        for chat in chats:
            col1, col2 = st.columns([5, 1])

            with col1:
                if st.button(chat["chat_name"], key=chat["id"], use_container_width=True):
                    st.session_state.current_chat = chat
                    st.rerun()

            with col2:
                if st.button("🗑", key="delete_" + chat["id"]):
                    delete_chat(chat["id"])
                    if (
                        "current_chat" in st.session_state
                        and st.session_state.current_chat["id"] == chat["id"]
                    ):
                        del st.session_state.current_chat
                    st.rerun()

        st.markdown("---")
        st.caption("🌐 Automatically replies in Hindi or English based on your question")