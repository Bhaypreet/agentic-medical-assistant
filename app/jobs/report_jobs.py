"""Off-request processing for uploaded reports.

/upload-report used to run the whole pipeline inline: one model call per
page, a sleep between pages, plus up to five rate-limit sleeps per call.
There was no request timeout, no cancellation and no progress signal, so
the client waited on an open socket and any proxy in front cut it first.

Uploads now return a job id immediately and the client polls. Job state
lives in the database rather than in process memory, so a second worker
can answer the poll. A dedicated queue (arq, RQ, Celery) is the next step
for running the work on separate machines; this keeps the work in-process
but off the request path.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import JSON, DateTime, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.logging_config import get_logger, request_id_var
from app.session.db import Base, SessionLocal, utcnow
from app.storage.uploads import discard_upload

logger = get_logger(__name__)

PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(16), default=PENDING)
    filename: Mapped[str] = mapped_column(String(255), default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="report-job")


def _set_status(job_id: str, status: str, *, result=None, error: str | None = None) -> None:

    with SessionLocal() as db:
        job = db.get(ReportJob, job_id)

        if job is None:  # pragma: no cover - the row is created first
            return

        job.status = status
        job.updated_at = utcnow()

        if result is not None:
            job.result = result

        if error is not None:
            job.error = error

        db.commit()


def _run(job_id: str, file_path, session_id: str, owner: str, request_id: str) -> None:

    token = request_id_var.set(request_id)

    try:
        _set_status(job_id, RUNNING)

        from app.agents.report_agent import report_agent

        result = report_agent(file_path=str(file_path), session_id=session_id, owner=owner)

        _set_status(job_id, SUCCEEDED, result=result)

        logger.info("Report job finished", extra={"job_id": job_id})

    except Exception as error:
        logger.exception("Report job failed", extra={"job_id": job_id})

        _set_status(
            job_id,
            FAILED,
            error=(
                "We couldn't process this report. Please check the file is a clear "
                "photo or the original PDF, and try again."
            ),
        )

        # Do not leak the underlying message to the caller; it is in the log.
        del error

    finally:
        # The source file has served its purpose; patient data must not
        # linger on disk beyond processing.
        discard_upload(file_path)
        request_id_var.reset(token)


def submit(file_path, session_id: str, owner: str, filename: str = "") -> str:
    """Queue a report for processing and return its job id."""

    job_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.add(
            ReportJob(
                id=job_id,
                session_id=session_id,
                owner=owner,
                status=PENDING,
                filename=filename,
            )
        )
        db.commit()

    _executor.submit(_run, job_id, file_path, session_id, owner, request_id_var.get())

    logger.info("Report job queued", extra={"job_id": job_id})

    return job_id


def get_job(job_id: str, owner: str) -> dict | None:
    """Job state, scoped to its owner so ids cannot be probed."""

    with SessionLocal() as db:
        job = db.scalar(select(ReportJob).where(ReportJob.id == job_id, ReportJob.owner == owner))

        if job is None:
            return None

        return {
            "job_id": job.id,
            "session_id": job.session_id,
            "status": job.status,
            "filename": job.filename,
            "result": job.result,
            "error": job.error,
        }


def purge_old_jobs(max_age_hours: int | None = None) -> int:
    """Remove finished jobs; their results contain report data."""

    hours = max_age_hours if max_age_hours is not None else settings.report_retention_hours
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    with SessionLocal() as db:
        result = db.execute(delete(ReportJob).where(ReportJob.created_at < cutoff))
        db.commit()

        return result.rowcount or 0


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
