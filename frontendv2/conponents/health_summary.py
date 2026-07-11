import streamlit as st


def show_summary(chat):

    if "summary" not in chat:

        return

    st.subheader("🩺 AI Health Summary")

    st.info(chat["summary"])