import streamlit as st


def show_summary(chat) -> None:

    summary = chat.get("summary")

    if not summary:
        return

    st.subheader("🩺 AI health summary")
    st.markdown(summary)
    st.caption("AI-generated and informational only — it does not replace a clinician.")
