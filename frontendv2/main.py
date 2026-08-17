import os
import tempfile

import streamlit as st

from styles import CSS

from api import (
    chat as chat_api,
    upload_report,
    transcribe_voice,
    download_report_pdf
)

from utils.storage import (
    save_chat,
    load_all_chats,
    create_chat
)

from components.sidebars import render_sidebar
from components.chat import (
    render_messages,
    add_message
)
from components.report import show_report
from components.health_summary import show_summary
from components.streaming import stream_text
from components.dashboards import render_dashboard


st.set_page_config(
    page_title="Agentic Medical Assistant",
    page_icon="🩺",
    layout="wide"
)

st.markdown(CSS, unsafe_allow_html=True)


if "current_chat" not in st.session_state:

    chats = load_all_chats()

    if len(chats) == 0:
        chat = create_chat()
        st.session_state.current_chat = chat
    else:
        st.session_state.current_chat = chats[0]


chat = st.session_state.current_chat

render_sidebar()

st.markdown(
    """
    <div class="app-header">
        <h1>🩺 Agentic Medical Assistant</h1>
        <p>AI-powered report analysis, symptom triage, and nearby-hospital finder</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.subheader(chat["chat_name"])

chat_tab, dashboard_tab = st.tabs(["💬 Chat", "📊 Health Dashboard"])

with dashboard_tab:
    render_dashboard(chat)

with chat_tab:

    if chat.get("summary"):
        show_summary(chat)

        if st.button("⬇️ Download Full Report (PDF)"):
            with st.spinner("Preparing PDF..."):
                pdf_bytes = download_report_pdf(chat["id"])
            st.download_button(
                "📄 Save PDF",
                data=pdf_bytes,
                file_name="health_report.pdf",
                mime="application/pdf"
            )

    if chat.get("report"):
        show_report(chat["report"])

    render_messages(chat)

    pending_prompt = st.session_state.pop("pending_prompt", None)

    if chat.get("suggestions") and not pending_prompt:

        st.caption("💡 You might also ask:")
        cols = st.columns(len(chat["suggestions"]))

        for i, suggestion in enumerate(chat["suggestions"]):
            with cols[i]:
                if st.button(suggestion, key=f"sugg_{chat['id']}_{i}", use_container_width=True):
                    st.session_state["pending_prompt"] = suggestion
                    st.rerun()

    upload_nonce_key = f"uploader_nonce_{chat['id']}"
    upload_nonce = st.session_state.get(upload_nonce_key, 0)

    mic_nonce_key = f"mic_nonce_{chat['id']}"
    mic_nonce = st.session_state.get(mic_nonce_key, 0)

    attach_col, mic_col, _ = st.columns([1, 1, 10])

    with attach_col:
        st.markdown('<div class="icon-btn">', unsafe_allow_html=True)
        with st.popover("📎"):
            st.caption("Upload a lab report (PDF or photo)")
            uploaded_file = st.file_uploader(
                "Upload",
                type=["pdf", "png", "jpg", "jpeg"],
                key=f"uploader_{chat['id']}_{upload_nonce}",
                label_visibility="collapsed"
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with mic_col:
        st.markdown('<div class="icon-btn">', unsafe_allow_html=True)
        with st.popover("🎙️"):
            st.caption("Record your question, then close this popover")
            audio_value = st.audio_input(
                "Record",
                key=f"mic_{chat['id']}_{mic_nonce}",
                label_visibility="collapsed"
            )
        st.markdown('</div>', unsafe_allow_html=True)

    if uploaded_file is not None and chat.get("uploaded_file") != uploaded_file.name:

        suffix = "." + uploaded_file.name.split(".")[-1].lower()

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.read())
            temp_path = tmp.name

        with st.spinner("Analyzing Medical Report..."):
            result = upload_report(temp_path, chat["id"])

        os.remove(temp_path)

        summary_text = result.get("summary", "")

        chat["report"] = result
        chat["summary"] = summary_text
        chat["chat_name"] = uploaded_file.name
        chat["uploaded_file"] = uploaded_file.name

        # also add it as a normal chat message, so it appears in the
        # conversation thread itself - not just as a floating info box
        if summary_text:
            add_message(
                chat,
                "assistant",
                f"📋 I've analyzed your report. Here's what I found:\n\n{summary_text}"
            )

        save_chat(chat)
        st.session_state.current_chat = chat

        st.session_state[upload_nonce_key] = upload_nonce + 1

        st.success("✅ Report Uploaded Successfully")
        st.rerun()

    voice_prompt = None

    if audio_value is not None:

        with st.spinner("Transcribing..."):
            try:
                voice_prompt = transcribe_voice(audio_value.read())
            except Exception as e:
                st.error(f"Could not transcribe audio: {e}")

        st.session_state[mic_nonce_key] = mic_nonce + 1

    typed_prompt = st.chat_input("Ask your medical question...")

    prompt = pending_prompt or voice_prompt or typed_prompt

    if prompt:

        add_message(chat, "user", prompt)
        save_chat(chat)

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):

            with st.spinner("Thinking..."):
                try:
                    response = chat_api(prompt, chat["id"])
                    answer = response.get("response", "Sorry, I couldn't generate a response.")
                    new_suggestions = response.get("suggestions", [])
                except Exception as e:
                    answer = f"❌ Error: {str(e)}"
                    new_suggestions = []

                streamed_text = stream_text(answer)

        add_message(chat, "assistant", streamed_text)
        chat["suggestions"] = new_suggestions

        save_chat(chat)
        st.session_state.current_chat = chat

        st.rerun()


st.divider()
st.caption("🩺 Agentic Medical Assistant | LangGraph + FastAPI + Groq + Whisper")