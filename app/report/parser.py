"""Extract text from an uploaded report, whether PDF or photograph.

The OCR path used to print the first 500 characters of the extracted text
to stdout on every upload. That is patient data going into production
logs, so it is now behind settings.debug_log_report_content, which the
config refuses to enable in production.
"""

import platform
from pathlib import Path

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

PDF_SUFFIXES = {".pdf"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class UnsupportedReportFile(ValueError):
    """The uploaded file is not a format we can read."""


def _configure_tesseract() -> None:

    if platform.system() == "Windows":  # pragma: no cover - platform specific
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def _log_extracted(text: str, source: str) -> None:
    """Record that text was extracted - and its content only on request."""

    logger.info("Extracted report text", extra={"source": source, "characters": len(text)})

    if settings.debug_log_report_content:
        logger.debug("Report content (debug only)", extra={"text": text[:500]})


def extract_text_from_pdf(pdf_path, max_pages: int | None = None) -> list[dict]:
    """Page text from a PDF, capped at max_pages.

    The cap matters: report_agent makes one model call per page, so an
    uncapped page count was an unbounded cost from a single request.
    """

    import pdfplumber

    limit = max_pages if max_pages is not None else settings.max_report_pages

    pages: list[dict] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)

        if total > limit:
            logger.warning(
                "Report exceeds the page limit; processing the first pages only",
                extra={"total_pages": total, "limit": limit},
            )

        for page_number, page in enumerate(pdf.pages[:limit], start=1):
            text = page.extract_text() or ""
            pages.append({"page": page_number, "text": text})

    joined = "".join(page["text"] for page in pages)
    _log_extracted(joined, "pdf")

    return pages


def _preprocess_for_ocr(image):
    """Improve OCR accuracy on dense lab-report tables."""

    from PIL import Image, ImageOps

    if image.width < 1800:
        scale = 1800 / image.width
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)

    image = image.convert("L")
    image = ImageOps.autocontrast(image)

    return image


def extract_text_from_image(image_path) -> list[dict]:

    import pytesseract
    from PIL import Image

    _configure_tesseract()

    with Image.open(str(image_path)) as image:
        text = pytesseract.image_to_string(_preprocess_for_ocr(image), config="--psm 6")

    _log_extracted(text, "ocr")

    return [{"page": 1, "text": text}]


def extract_report_pages(file_path) -> list[dict]:

    suffix = Path(str(file_path)).suffix.lower()

    if suffix in PDF_SUFFIXES:
        return extract_text_from_pdf(file_path)

    if suffix in IMAGE_SUFFIXES:
        return extract_text_from_image(file_path)

    raise UnsupportedReportFile(f"Unsupported file type: {suffix or '(none)'}")
