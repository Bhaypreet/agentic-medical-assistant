"""Session state, backed by a database.

The previous implementation kept every session in one JSON file that was
loaded once at import, mutated in memory and fully rewritten on every
message. That failed in four separate ways: a second worker got a
divergent in-memory copy, a crash mid-write truncated every session, the
threadpool that runs FastAPI's sync endpoints raced on both the dict and
the file, and an ephemeral container filesystem lost all of it on restart.

The public method names are unchanged so callers did not have to move in
the same commit, but every read now takes an `owner` so that knowing a
session id is not sufficient to read someone else's data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.logging_config import get_logger
from app.session.db import ChatMessage, ChatSession, SessionLocal, utcnow

logger = get_logger(__name__)

ANONYMOUS = "anonymous"


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops the timezone on round-trip; treat naive values as UTC."""

    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value


class SessionNotFound(Exception):
    """Raised when a session does not exist, or is not owned by the caller."""


class SessionManager:
    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _get(self, db, session_id: str, owner: str) -> ChatSession | None:
        return db.scalar(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.owner == owner,
            )
        )

    def _get_or_create(self, db, session_id: str, owner: str) -> ChatSession:

        record = self._get(db, session_id, owner)

        if record is not None:
            return record

        # A session id that exists under a different owner must not be
        # silently adopted - that would be the original IDOR by another
        # route. Reject it instead.
        conflicting = db.scalar(select(ChatSession).where(ChatSession.id == session_id))

        if conflicting is not None:
            logger.warning(
                "Rejected cross-owner session access",
                extra={"session_id": session_id},
            )
            raise SessionNotFound(session_id)

        record = ChatSession(id=session_id, owner=owner)
        db.add(record)
        db.flush()

        return record

    def _expire_pending(self, record: ChatSession) -> None:
        """Drop pending flags that are older than the configured TTL.

        Without this a failed doctor lookup left pending_specialist set
        forever, and every later message was misread as a location reply.
        """

        cutoff = utcnow() - timedelta(seconds=settings.pending_state_ttl_seconds)

        if _as_utc(record.pending_specialist_at) and _as_utc(record.pending_specialist_at) < cutoff:
            record.pending_specialist = None
            record.pending_specialist_at = None

        clarified_at = _as_utc(record.pending_clarification_at)

        if clarified_at and clarified_at < cutoff:
            record.pending_clarification = None
            record.pending_clarification_at = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def create_session(self, session_id: str, owner: str = ANONYMOUS) -> None:
        with SessionLocal() as db:
            self._get_or_create(db, session_id, owner)
            db.commit()

    def clear_chat(self, session_id: str, owner: str = ANONYMOUS) -> str | None:
        """Delete a session. Returns its report_id so the caller can also
        remove the report's vector store and uploaded file."""

        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return None

            report_id = record.report_id
            db.delete(record)
            db.commit()

            return report_id

    # ------------------------------------------------------------------
    # reports
    # ------------------------------------------------------------------

    def save_report(self, session_id: str, report_id: str, owner: str = ANONYMOUS) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            record.report_id = report_id
            db.commit()

    def get_report(self, session_id: str, owner: str = ANONYMOUS) -> str | None:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)
            return record.report_id if record else None

    def save_report_data(
        self,
        session_id: str,
        analysis: list,
        summary: str,
        owner: str = ANONYMOUS,
    ) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            record.report_analysis = analysis
            record.report_summary = summary
            db.commit()

    def get_report_data(self, session_id: str, owner: str = ANONYMOUS) -> dict[str, Any]:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return {"analysis": [], "summary": ""}

            return {
                "analysis": record.report_analysis or [],
                "summary": record.report_summary or "",
            }

    # ------------------------------------------------------------------
    # messages
    # ------------------------------------------------------------------

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        owner: str = ANONYMOUS,
    ) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            db.add(ChatMessage(session_id=record.id, role=role, content=content))
            record.updated_at = utcnow()
            db.commit()

    def get_messages(
        self,
        session_id: str,
        owner: str = ANONYMOUS,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        """Most recent messages, oldest first.

        The old implementation truncated the stored history to 20 entries,
        destroying the conversation. Everything is retained now; the limit
        applies only to what is handed to the model.
        """

        limit = limit or settings.max_history_messages

        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return []

            rows = db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(limit)
            ).all()

            return [{"role": row.role, "content": row.content} for row in reversed(rows)]

    # ------------------------------------------------------------------
    # naming
    # ------------------------------------------------------------------

    def set_chat_name(self, session_id: str, name: str, owner: str = ANONYMOUS) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            record.chat_name = name
            db.commit()

    def get_chat_name(self, session_id: str, owner: str = ANONYMOUS) -> str:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)
            return record.chat_name if record else "New Chat"

    def list_sessions(self, owner: str = ANONYMOUS, limit: int = 100) -> list[dict[str, Any]]:
        """Sessions for one owner, most recently updated first.

        Replaces get_all_sessions(), which returned every session in the
        store to every caller with no pagination.
        """

        with SessionLocal() as db:
            rows = db.scalars(
                select(ChatSession)
                .where(ChatSession.owner == owner)
                .order_by(ChatSession.updated_at.desc())
                .limit(limit)
            ).all()

            return [
                {
                    "id": row.id,
                    "chat_name": row.chat_name,
                    "has_report": row.report_id is not None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------
    # pending specialist (waiting for the patient's location)
    # ------------------------------------------------------------------

    def set_pending_specialist(
        self,
        session_id: str,
        specialist: str,
        owner: str = ANONYMOUS,
    ) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            record.pending_specialist = specialist
            record.pending_specialist_at = utcnow()
            db.commit()

    def get_pending_specialist(self, session_id: str, owner: str = ANONYMOUS) -> str | None:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return None

            self._expire_pending(record)
            db.commit()

            return record.pending_specialist

    def clear_pending_specialist(self, session_id: str, owner: str = ANONYMOUS) -> None:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return

            record.pending_specialist = None
            record.pending_specialist_at = None
            db.commit()

    # ------------------------------------------------------------------
    # pending clarification (one follow-up question before triage)
    # ------------------------------------------------------------------

    def set_pending_clarification(
        self,
        session_id: str,
        original_query: str,
        owner: str = ANONYMOUS,
    ) -> None:
        with SessionLocal() as db:
            record = self._get_or_create(db, session_id, owner)
            record.pending_clarification = original_query
            record.pending_clarification_at = utcnow()
            db.commit()

    def get_pending_clarification(self, session_id: str, owner: str = ANONYMOUS) -> str | None:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return None

            self._expire_pending(record)
            db.commit()

            return record.pending_clarification

    def clear_pending_clarification(self, session_id: str, owner: str = ANONYMOUS) -> None:
        with SessionLocal() as db:
            record = self._get(db, session_id, owner)

            if record is None:
                return

            record.pending_clarification = None
            record.pending_clarification_at = None
            db.commit()


session_manager = SessionManager()
