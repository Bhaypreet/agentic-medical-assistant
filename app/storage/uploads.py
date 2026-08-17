"""Safe handling of uploaded report files.

The previous implementation built the destination path from the
client-supplied filename (`os.path.join("uploads", file.filename)`), so a
filename of "../app/api/routes.py" overwrote application source. It also
streamed an arbitrary body to disk with no size cap, and validated the
extension only in the Streamlit widget.
"""

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
}

# Leading bytes that must match the claimed type. Cheap defence against a
# file that merely renames itself to .pdf.
_MAGIC = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}

_CHUNK = 1024 * 1024


def _extension_of(filename: str | None) -> str:

    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload is missing a filename.",
        )

    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    return suffix


def safe_display_name(filename: str | None) -> str:
    """A filename that is safe to store as a chat title and echo back."""

    stem = Path(filename or "report").name
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "", stem).strip()

    return cleaned[:120] or "report"


def store_upload(file: UploadFile) -> Path:
    """Write an upload to a server-generated path, enforcing type and size.

    Returns the path written. Raises HTTPException and removes the partial
    file if the upload is rejected.
    """

    suffix = _extension_of(file.filename)

    if file.content_type and file.content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {file.content_type}.",
        )

    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    # The client's filename is never used to build the path.
    destination = settings.upload_dir / f"{uuid.uuid4()}{suffix}"

    written = 0
    first_chunk = True

    try:
        with destination.open("wb") as buffer:
            while chunk := file.file.read(_CHUNK):
                if first_chunk:
                    _reject_if_magic_mismatch(chunk, suffix)
                    first_chunk = False

                written += len(chunk)

                if written > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,  # Content Too Large
                        detail=(
                            "File is too large. Maximum size is "
                            f"{settings.max_upload_bytes // (1024 * 1024)} MB."
                        ),
                    )

                buffer.write(chunk)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    if written == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    logger.info("Stored upload", extra={"bytes": written, "suffix": suffix})

    return destination


def _reject_if_magic_mismatch(head: bytes, suffix: str) -> None:

    signatures = _MAGIC.get(suffix)

    if signatures and not any(head.startswith(sig) for sig in signatures):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File contents do not look like a {suffix.lstrip('.').upper()} file.",
        )


def discard_upload(path: Path | str | None) -> None:
    """Remove a processed upload. Patient data must not linger on disk."""

    if not path:
        return

    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove processed upload")
