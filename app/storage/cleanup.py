"""Retention for uploaded reports and their vector stores.

Every upload previously left a permanent copy in uploads/ and a permanent
FAISS index in report_vectorstore/<uuid>/. Nothing removed either, and
deleting a chat orphaned both - unencrypted patient data accumulating
indefinitely.
"""

import shutil
import threading
import time
from pathlib import Path

from app.api.security import validate_report_id
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


def delete_report_store(report_id: str | None) -> None:
    """Remove one report's vector store, by id."""

    if not report_id:
        return

    try:
        safe_id = validate_report_id(report_id)
    except ValueError:
        logger.warning("Refusing to delete a store with a malformed report id")
        return

    target = (settings.report_vectorstore_dir / safe_id).resolve()
    root = settings.report_vectorstore_dir.resolve()

    if root not in target.parents:
        logger.warning("Refusing to delete a path outside the report store root")
        return

    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
        logger.info("Deleted report vector store", extra={"report_id": safe_id})


def _older_than(path: Path, seconds: float) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) > seconds
    except OSError:
        return False


def purge_expired(retention_hours: int | None = None) -> dict[str, int]:
    """Delete uploads and report stores past their retention window."""

    hours = retention_hours if retention_hours is not None else settings.report_retention_hours
    max_age = hours * 3600

    removed_uploads = 0
    removed_stores = 0

    upload_dir = settings.upload_dir

    if upload_dir.is_dir():
        for item in upload_dir.iterdir():
            if item.is_file() and _older_than(item, max_age):
                item.unlink(missing_ok=True)
                removed_uploads += 1

    store_dir = settings.report_vectorstore_dir

    if store_dir.is_dir():
        for item in store_dir.iterdir():
            if item.is_dir() and _older_than(item, max_age):
                shutil.rmtree(item, ignore_errors=True)
                removed_stores += 1

    # Finished job rows hold the report result, which is patient data.
    from app.auth.service import purge_expired_tokens
    from app.jobs.report_jobs import purge_old_jobs

    removed_jobs = purge_old_jobs(hours)
    removed_tokens = purge_expired_tokens()

    if removed_uploads or removed_stores or removed_jobs or removed_tokens:
        logger.info(
            "Retention sweep complete",
            extra={
                "uploads_removed": removed_uploads,
                "stores_removed": removed_stores,
                "jobs_removed": removed_jobs,
                "tokens_removed": removed_tokens,
            },
        )

    return {
        "uploads": removed_uploads,
        "stores": removed_stores,
        "jobs": removed_jobs,
        "tokens": removed_tokens,
    }


def start_retention_worker(interval_seconds: int = 3600):
    """Run purge_expired() periodically. Returns a callable that stops it."""

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_seconds):
            try:
                purge_expired()
            except Exception:
                logger.exception("Retention sweep failed")

    thread = threading.Thread(target=_loop, name="retention-worker", daemon=True)
    thread.start()

    def _stop() -> None:
        stop.set()

    return _stop
