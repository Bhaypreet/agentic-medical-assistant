import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
from io import BytesIO

from app.api.schemas import ChatRequest
from app.agents.graph import graph
from app.agents.report_agent import report_agent
from app.agents.report_chat_agent import report_chat_agent
from app.session.session_manager import session_manager
from app.tools.suggestion_generator import generate_suggestions
from app.tools.voice import transcribe_audio
from app.tools.pdf_report_generator import generate_report_pdf

router = APIRouter()


@router.get("/")
def home():
    return {"message": "Agentic Medical Assistant API Running 🚀"}


@router.get("/health")
def health():
    return {"status": "healthy"}


@router.post("/chat")
def chat(request: ChatRequest):

    history = session_manager.get_messages(request.session_id)

    result = graph.invoke(
        {
            "query": request.query,
            "pdf_path": "",
            "session_id": request.session_id,
            "report_id": "",
            "location": request.location,
            "severity": 0,
            "report_analysis": [],
            "response": "",
            "chat_history": history
        }
    )

    response_text = result.get("response", "No response generated.")

    session_manager.add_message(request.session_id, "user", request.query)
    session_manager.add_message(request.session_id, "assistant", response_text)

    suggestions = generate_suggestions(request.query, response_text)

    return {
        "response": response_text,
        "suggestions": suggestions
    }


@router.post("/upload-report")
async def upload_report(
    session_id: str,
    file: UploadFile = File(...)
):

    os.makedirs("uploads", exist_ok=True)

    file_path = os.path.join("uploads", file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = report_agent(file_path=file_path, session_id=session_id)

    return result


@router.post("/report-chat")
def report_chat(session_id: str, question: str):

    answer = report_chat_agent(session_id=session_id, question=question)

    return {"response": answer}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Voice input - converts recorded speech to text."""

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        text = transcribe_audio(tmp_path)
    finally:
        os.remove(tmp_path)

    return {"text": text}

@router.get("/download-report")
def download_report(session_id: str):
    """Generates a downloadable PDF of the patient's analyzed report."""

    report_data = session_manager.get_report_data(session_id)

    pdf_bytes = generate_report_pdf(
        summary_text=report_data.get("summary", "No summary available."),
        analysis=report_data.get("analysis", [])
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=health_report.pdf"}
    )