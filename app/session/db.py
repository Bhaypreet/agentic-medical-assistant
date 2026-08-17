"""Database engine and schema for session state.

Replaces the previous single-JSON-file store. SQLAlchemy is used rather
than raw sqlite3 so the same code runs against Postgres in production by
changing DATABASE_URL alone.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Which authenticated principal this session belongs to. Every read is
    # scoped by this, so knowing a session id is not enough to read it.
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="anonymous")

    chat_name: Mapped[str] = mapped_column(String(255), default="New Chat")

    report_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    report_summary: Mapped[str] = mapped_column(Text, default="")
    report_analysis: Mapped[list] = mapped_column(JSON, default=list)

    pending_specialist: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pending_specialist_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pending_clarification: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_clarification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


Index("ix_chat_sessions_owner_updated", ChatSession.owner, ChatSession.updated_at)


def _build_engine():

    url = settings.database_url
    connect_args = {}
    kwargs = {}

    if url.startswith("sqlite"):
        # FastAPI runs sync endpoints across a threadpool, so the
        # connection is handed between threads.
        connect_args["check_same_thread"] = False

        if ":memory:" in url:
            # Every connection to :memory: would otherwise get its own
            # empty database; one shared connection keeps tests coherent.
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool

    engine = create_engine(
        url, connect_args=connect_args, pool_pre_ping=True, future=True, **kwargs
    )

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            # WAL lets readers and a writer proceed concurrently; the busy
            # timeout makes concurrent writers wait rather than raising
            # "database is locked".
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


engine = _build_engine()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if they do not exist. Called once at startup."""
    Base.metadata.create_all(engine)
