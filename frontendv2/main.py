import streamlit as st

import api
from components.chat import render_messages
from components.dashboards import render_dashboard
from components.health_summary import show_summary
from components.report import show_report
from components.sidebars import render_sidebar
from config import API_KEY, FASTAPI_URL
from styles import CSS
from utils.storage import create_chat, load_all_chats, load_messages, refresh_sessions, save_chat

st.set_page_config(
    page_title="Agentic Medical Assistant",
    page_icon="🩺",
    layout="wide",
)

st.markdown(CSS, unsafe_allow_html=True)


if "current_chat" not in st.session_state:
    chats = load_all_chats()
    st.session_state.current_chat = chats[0] if chats else create_chat()

chat = st.session_state.current_chat

render_sidebar()

st.markdown(
    """
    <div class="app-header">
        <h1>🩺 Agentic Medical Assistant</h1>
        <p>AI-powered report analysis, symptom triage, and nearby-hospital finder</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not API_KEY:
    st.info(
        f"No API key is configured, so this app is talking to `{FASTAPI_URL}` "
        "unauthenticated. Set `MEDICAL_ASSISTANT_API_KEY` before deploying — "
        "without it, anyone reaching the backend can read the chats it stores.",
        icon="🔑",
    )

st.subheader(chat.get("chat_name", "New Chat"))

chat_tab, dashboard_tab = st.tabs(["💬 Chat", "📊 Health Dashboard"])

with dashboard_tab:
    render_dashboard(chat)

with chat_tab:
    if chat.get("summary"):
        show_summary(chat)

        if st.button("⬇️ Download full report (PDF)"):
            try:
                with st.spinner("Preparing PDF…"):
                    pdf_bytes = api.download_report_pdf(chat["id"])
            except api.ApiError as error:
                st.error(str(error))
            else:
                st.download_button(
                    "📄 Save PDF",
                    data=pdf_bytes,
                    file_name="health_report.pdf",
                    mime="application/pdf",
                )

    if chat.get("report"):
        show_report(chat["report"])

    render_messages(load_messages(chat["id"]))

    pending_prompt = st.session_state.pop("pending_prompt", None)

    if chat.get("suggestions") and not pending_prompt:
        st.caption("💡 You might also ask:")
        columns = st.columns(len(chat["suggestions"]))

        for index, suggestion in enumerate(chat["suggestions"]):
            with columns[index]:
                if st.button(
                    suggestion, key=f"sugg_{chat['id']}_{index}", use_container_width=True
                ):
                    st.session_state["pending_prompt"] = suggestion
                    st.rerun()

    upload_nonce_key = f"uploader_nonce_{chat['id']}"
    upload_nonce = st.session_state.get(upload_nonce_key, 0)

    mic_nonce_key = f"mic_nonce_{chat['id']}"
    mic_nonce = st.session_state.get(mic_nonce_key, 0)

    attach_column, mic_column, _ = st.columns([1, 1, 10])

    with attach_column, st.popover("📎"):
        st.caption("Upload a lab report (PDF or photo, max 15 MB)")
        uploaded_file = st.file_uploader(
            "Upload",
            type=["pdf", "png", "jpg", "jpeg"],
            key=f"uploader_{chat['id']}_{upload_nonce}",
            label_visibility="collapsed",
        )

    with mic_column, st.popover("🎙️"):
        st.caption("Record your question, then close this popover")
        audio_value = st.audio_input(
            "Record",
            key=f"mic_{chat['id']}_{mic_nonce}",
            label_visibility="collapsed",
        )

    # ---------------------------------------------------------- upload

    if uploaded_file is not None:
        status = st.status(f"Analysing {uploaded_file.name}…", expanded=True)

        try:
            with status:
                st.write("Uploading…")

                job = api.upload_report(
                    file_bytes=uploaded_file.getvalue(),
                    filename=uploaded_file.name,
                    session_id=chat["id"],
                )

                st.write("Reading the report — this can take a minute for a long PDF.")

                result = api.wait_for_report(job["job_id"])

        except api.ApiError as error:
            status.update(label="Upload failed", state="error")
            st.error(str(error))

        else:
            status.update(label="Report analysed", state="complete")

            chat["report"] = result
            chat["summary"] = result.get("summary", "")
            chat["chat_name"] = uploaded_file.name
            chat["uploaded_file"] = uploaded_file.name

            for warning in (result.get("outcome") or {}).get("warnings", []):
                st.warning(warning)

            save_chat(chat)
            refresh_sessions()

            st.session_state.current_chat = chat
            st.session_state[upload_nonce_key] = upload_nonce + 1

            st.rerun()

    # ----------------------------------------------------------- voice

    voice_prompt = None

    if audio_value is not None:
        with st.spinner("Transcribing…"):
            try:
                voice_prompt = api.transcribe_voice(audio_value.read())
            except api.ApiError as error:
                st.error(str(error))

        st.session_state[mic_nonce_key] = mic_nonce + 1

    # ------------------------------------------------------------ chat

    typed_prompt = st.chat_input("Ask your medical question…")

    prompt = pending_prompt or voice_prompt or typed_prompt

    if prompt:
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("_Thinking…_")

            answer = ""
            suggestions = []

            try:
                for event, payload in api.chat_stream(prompt, chat["id"]):
                    if event == "progress":
                        placeholder.markdown(f"_{payload.get('label', 'Working…')}_")
                    elif event == "message":
                        answer = payload.get("response", "")
                        placeholder.markdown(answer)
                    elif event == "suggestions":
                        suggestions = payload.get("suggestions", [])
                    elif event == "error":
                        raise api.ApiError(payload.get("detail", "Something went wrong."))

            except api.ApiError as error:
                answer = ""
                placeholder.error(str(error))

            if answer:
                placeholder.markdown(answer)

        if answer:
            chat["suggestions"] = suggestions
            save_chat(chat)
            refresh_sessions()
            st.session_state.current_chat = chat
            st.rerun()


st.divider()
st.caption("🩺 Agentic Medical Assistant — informational only, not a medical diagnosis.")
