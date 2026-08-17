import json
import os
import tempfile
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.agents.graph import build_state, graph
from app.api.rate_limit import limiter
from app.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryResponse,
    JobStatus,
    ReadinessResponse,
    SessionSummary,
    TranscriptionResponse,
    UploadAccepted,
)
from app.api.security import require_owner, validate_session_id
from app.config import settings
from app.jobs import report_jobs
from app.logging_config import get_logger
from app.rag import retriever as rag_retriever
from app.safety import apply_safety
from app.session.session_manager import session_manager
from app.storage.cleanup import delete_report_store
from app.storage.uploads import safe_display_name, store_upload
from app.tools.pdf_report_generator import generate_report_pdf
from app.tools.suggestion_generator import generate_suggestions

logger = get_logger(__name__)

router = APIRouter()

MAX_AUDIO_BYTES = 25 * 1024 * 1024


@router.get("/", tags=["meta"])
def home():
    return {"message": "Agentic Medical Assistant API"}


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    """Liveness: is this process running at all."""
    return {"status": "alive"}


@router.get("/ready", response_model=ReadinessResponse, tags=["meta"])
def ready(request: Request):
    """Readiness: can this process actually serve traffic.

    /health used to return a hardcoded "healthy" and stayed green while
    the vector store was missing and the credential was invalid, so an
    orchestrator kept routing traffic to a broken instance.
    """

    checks: dict[str, str] = {}

    try:
        session_manager.list_sessions(owner="__readiness__", limit=1)
        checks["database"] = "ok"
    except Exception:
        logger.exception("Readiness: database check failed")
        checks["database"] = "failed"

    checks["credentials"] = "ok" if settings.groq_api_key else "missing"
    checks["knowledge_base"] = "ok" if rag_retriever.is_ready() else "degraded"

    if checks["database"] != "ok" or checks["credentials"] != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not ready", "checks": checks},
        )

    return {"status": "ready", "checks": checks}


# ---------------------------------------------------------------- chat


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
@limiter.limit(settings.chat_rate_limit)
def chat(
    request: Request,
    response: Response,
    payload: ChatRequest,
    owner: str = Depends(require_owner),
):

    session_id = validate_session_id(payload.session_id)

    history = session_manager.get_messages(session_id, owner=owner)

    result = graph.invoke(
        build_state(
            query=payload.query,
            session_id=session_id,
            owner=owner,
            location=payload.location,
            chat_history=history,
        )
    )

    answer = apply_safety(
        result.get("response") or "I wasn't able to produce an answer to that.",
        severity=result.get("severity"),
        emergency=result.get("emergency"),
    )

    session_manager.add_message(session_id, "user", payload.query, owner=owner)
    session_manager.add_message(session_id, "assistant", answer, owner=owner)

    return {
        "response": answer,
        "suggestions": generate_suggestions(payload.query, answer),
        "session_id": session_id,
    }


@router.get("/history", response_model=HistoryResponse, tags=["chat"])
def history(session_id: str, owner: str = Depends(require_owner), limit: int = 200):
    """The conversation, from the server.

    The frontend used to keep its own parallel copy, which drifted from
    the backend's immediately - the report summary was added to one and
    not the other, so the model never knew a report had been discussed.
    """

    session_id = validate_session_id(session_id)

    return {
        "session_id": session_id,
        "messages": session_manager.get_messages(session_id, owner=owner, limit=min(limit, 500)),
    }


@router.get("/sessions", response_model=list[SessionSummary], tags=["chat"])
def list_sessions(owner: str = Depends(require_owner), limit: int = 100):
    return session_manager.list_sessions(owner=owner, limit=min(limit, 200))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["chat"])
def delete_session(session_id: str, owner: str = Depends(require_owner)):
    """Delete a chat and everything derived from it."""

    session_id = validate_session_id(session_id)

    report_id = session_manager.clear_chat(session_id, owner=owner)

    # Deleting a chat used to orphan its vector store on disk forever.
    delete_report_store(report_id)

    return None


# -------------------------------------------------------------- reports


@router.post(
    "/upload-report",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["reports"],
)
@limiter.limit(settings.upload_rate_limit)
def upload_report(
    request: Request,
    response: Response,
    session_id: str,
    file: UploadFile = File(...),
    owner: str = Depends(require_owner),
):
    """Accept a report and process it off the request path.

    Returns a job id immediately; poll /report-status/{job_id}.
    """

    session_id = validate_session_id(session_id)

    stored_path = store_upload(file)
    display_name = safe_display_name(file.filename)

    session_manager.set_chat_name(session_id, display_name, owner=owner)

    job_id = report_jobs.submit(
        file_path=stored_path,
        session_id=session_id,
        owner=owner,
        filename=display_name,
    )

    return {"job_id": job_id, "session_id": session_id, "status": "pending"}


@router.get("/report-status/{job_id}", response_model=JobStatus, tags=["reports"])
def report_status(job_id: str, owner: str = Depends(require_owner)):

    job = report_jobs.get_job(job_id, owner=owner)

    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return job


@router.get("/download-report", tags=["reports"])
def download_report(session_id: str, owner: str = Depends(require_owner)):
    """A PDF of the patient's analysed report."""

    session_id = validate_session_id(session_id)

    report_data = session_manager.get_report_data(session_id, owner=owner)

    if not report_data.get("analysis") and not report_data.get("summary"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analysed report is available for this chat.",
        )

    pdf_bytes = generate_report_pdf(
        summary_text=report_data.get("summary", ""),
        analysis=report_data.get("analysis", []),
    )

    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="health_report.pdf"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------- voice


@router.post("/transcribe", response_model=TranscriptionResponse, tags=["voice"])
@limiter.limit(settings.transcribe_rate_limit)
async def transcribe(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    owner: str = Depends(require_owner),
):
    from app.tools.voice import transcribe_audio

    payload = await file.read(MAX_AUDIO_BYTES + 1)

    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,  # Content Too Large
            detail="Recording is too long.",
        )

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Recording is empty.",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        text = transcribe_audio(tmp_path)
    finally:
        os.unlink(tmp_path)

    return {"text": text}


# ------------------------------------------------------------ streaming

# Human-readable progress for each node, so the client can show what the
# assistant is actually doing instead of a static spinner.
NODE_LABELS = {
    "ask_clarification_node": "Thinking about what to ask you…",
    "clarify_answer_node": "Assessing what you've described…",
    "rag_node": "Looking this up…",
    "diet_node": "Building a nutrition plan…",
    "doctor_node": "Finding nearby clinics…",
    "resume_doctor_node": "Finding nearby clinics…",
    "hospital_search_node": "Searching the facility directory…",
    "ask_location_node": "Preparing a recommendation…",
    "report_chat_node": "Reading your report…",
    "report_node": "Analysing your report…",
    "greeting_node": "Saying hello…",
}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream", tags=["chat"])
@limiter.limit(settings.chat_rate_limit)
def chat_stream(
    request: Request,
    response: Response,
    payload: ChatRequest,
    owner: str = Depends(require_owner),
):
    """Server-sent events for a chat turn.

    The frontend previously faked a typewriter effect by sleeping 20ms per
    token over an answer that had already arrived in full, which added
    roughly ten seconds of latency to a long reply rather than hiding any.
    Progress is now reported as the graph actually runs.
    """

    session_id = validate_session_id(payload.session_id)
    history = session_manager.get_messages(session_id, owner=owner)

    state = build_state(
        query=payload.query,
        session_id=session_id,
        owner=owner,
        location=payload.location,
        chat_history=history,
    )

    def events():

        answer = ""
        severity = None
        emergency = None

        try:
            for update in graph.stream(state, stream_mode="updates"):
                for node, changes in (update or {}).items():

                    label = NODE_LABELS.get(node)

                    if label:
                        yield _sse("progress", {"step": node, "label": label})

                    if not isinstance(changes, dict):
                        continue

                    answer = changes.get("response") or answer
                    severity = changes.get("severity", severity)
                    emergency = changes.get("emergency", emergency)

        except Exception:
            logger.exception("Streaming chat turn failed")
            yield _sse("error", {"detail": "Something went wrong. Please try again."})
            return

        final = apply_safety(
            answer or "I wasn't able to produce an answer to that.",
            severity=severity,
            emergency=emergency,
        )

        session_manager.add_message(session_id, "user", payload.query, owner=owner)
        session_manager.add_message(session_id, "assistant", final, owner=owner)

        yield _sse("message", {"response": final})
        yield _sse("suggestions", {"suggestions": generate_suggestions(payload.query, final)})
        yield _sse("done", {"session_id": session_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
