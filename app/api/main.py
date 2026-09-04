import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.auth_routes import router as auth_router
from app.api.rate_limit import limiter
from app.api.routes import router
from app.config import settings
from app.jobs import report_jobs
from app.logging_config import configure_logging, get_logger, request_id_var
from app.session.db import init_db
from app.session.session_manager import SessionNotFound
from app.storage.cleanup import start_retention_worker

configure_logging()

logger = get_logger(__name__)


async def _warm_retrieval(app: FastAPI) -> None:
    """Load the knowledge base without blocking startup.

    Loading the embedding model can take minutes on a small instance -
    it may have to download the model first. Doing that inline blocked
    the event loop, so uvicorn never finished startup, never served HTTP,
    and the platform's port scan failed even though gunicorn was bound.

    Retrieval is lazy anyway: until this finishes, general questions fall
    back to the model's own knowledge and /ready reports "degraded".
    """

    from app.rag.retriever import warm_up

    try:
        app.state.retrieval_ready = await asyncio.to_thread(warm_up)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Knowledge base warm-up failed")
        app.state.retrieval_ready = False

    if app.state.retrieval_ready:
        logger.info("Knowledge base ready")
    else:
        logger.error(
            "Knowledge base unavailable; general medical questions will "
            "return a degraded response. Run 'python -m app.rag.ingest'."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start-up and shut-down work.

    Retrieval used to load at module import, so a missing vectorstore
    directory made the whole application fail to import and the container
    restart-loop. Warm-up happens here instead, off the startup path, and
    a failure is recorded and surfaced by the readiness probe rather than
    killing the process.
    """

    logger.info("Starting service", extra={"environment": settings.environment})

    init_db()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.report_vectorstore_dir.mkdir(parents=True, exist_ok=True)

    app.state.retrieval_ready = False
    warm_task = asyncio.create_task(_warm_retrieval(app))

    stop_cleanup = start_retention_worker()

    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
            logger.info("Error tracking enabled")
        except ImportError:
            logger.warning("SENTRY_DSN is set but sentry-sdk is not installed")

    yield

    warm_task.cancel()
    stop_cleanup()
    report_jobs.shutdown()
    logger.info("Shutting down")


app = FastAPI(
    title="Agentic Medical Assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a correlation id and record timing for every request."""

    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)

    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled error",
            extra={"path": request.url.path, "method": request.method},
        )
        raise
    finally:
        request_id_var.reset(token)

    duration_ms = round((time.perf_counter() - started) * 1000, 1)

    logger.info(
        "Request handled",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status": response.status_code,
            "duration_ms": duration_ms,
        },
    )

    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(SessionNotFound)
async def session_not_found_handler(_request: Request, _exc: SessionNotFound):
    # Deliberately indistinguishable from "does not exist", so the
    # response cannot be used to probe for other people's session ids.
    return JSONResponse(status_code=404, content={"detail": "Session not found."})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, _exc: Exception):
    # Never leak a stack trace or internal message to the caller; the
    # correlation id in the response header ties it to the server log.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error.", "request_id": request_id_var.get()},
    )


app.include_router(auth_router)
app.include_router(router)
