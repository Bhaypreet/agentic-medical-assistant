import streamlit as st


def render_history(chat):

    st.divider()

    st.subheader("Conversation")

    for message in chat["messages"]:

        with st.chat_message(
            message["role"]
        ):

            st.markdown(
                message["content"]
            )