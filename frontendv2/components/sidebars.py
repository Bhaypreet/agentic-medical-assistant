import streamlit as st

from utils.storage import create_chat, delete_chat, load_all_chats


def render_sidebar() -> None:

    with st.sidebar:
        st.title("🩺 Medical Assistant")
        st.markdown("---")

        if st.button("➕ New chat", use_container_width=True):
            st.session_state.current_chat = create_chat()
            st.rerun()

        st.markdown("---")
        st.subheader("💬 Chats")

        chats = load_all_chats()

        if not chats:
            st.caption("No chats yet.")

        for chat in chats:
            label_column, delete_column = st.columns([5, 1])

            label = chat["chat_name"]

            if chat.get("has_report"):
                label = f"📄 {label}"

            with label_column:
                if st.button(label, key=chat["id"], use_container_width=True):
                    st.session_state.current_chat = chat
                    st.rerun()

            with delete_column:
                if st.button("🗑", key=f"delete_{chat['id']}", help="Delete this chat"):
                    delete_chat(chat["id"])

                    current = st.session_state.get("current_chat")

                    if current and current["id"] == chat["id"]:
                        del st.session_state.current_chat

                    st.rerun()

        st.markdown("---")
        st.caption("🌐 Replies in the language you write in.")
        st.caption("⚠️ Informational only — not a medical diagnosis.")
