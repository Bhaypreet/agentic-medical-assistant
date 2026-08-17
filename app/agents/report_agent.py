"""Process an uploaded report end to end.

The previous pipeline could produce a confident summary of a report it had
never read: detect_report_type matched a twelve-entry keyword list and
returned None for anything else, so unrecognised pages were silently
skipped; every extraction failure was swallowed by a printed message; and
if that left all_reports empty, generate_summary([]) still asked the model
for "Overall Summary / Abnormal Findings / Recommendations".
"""

from dataclasses import dataclass, field

from app.agents.summary_agent import generate_summary
from app.logging_config import get_logger
from app.report.analyzer import analyze_report
from app.report.extractor import ExtractionFailed, extract_structured_report
from app.report.parser import extract_report_pages
from app.report.section_detector import detect_report_type
from app.report_rag.ingest import ingest_report
from app.session.session_manager import ANONYMOUS, session_manager

logger = get_logger(__name__)

NO_VALUES_MESSAGE = (
    "## Could not read this report\n\n"
    "No laboratory values could be extracted from the file you uploaded.\n\n"
    "This usually means one of:\n\n"
    "- the photo is blurred, cropped, or taken at an angle\n"
    "- the PDF is a scan whose text layer is missing\n"
    "- the document is not a laboratory report\n\n"
    "Please try a clearer, straight-on photo of the full page, or upload the "
    "original PDF from your laboratory."
)


@dataclass
class ReportOutcome:
    """What actually happened, so the caller can tell the patient."""

    pages_total: int = 0
    pages_analyzed: int = 0
    pages_skipped: int = 0
    pages_failed: int = 0
    unresolved_values: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pages_total": self.pages_total,
            "pages_analyzed": self.pages_analyzed,
            "pages_skipped": self.pages_skipped,
            "pages_failed": self.pages_failed,
            "unresolved_values": self.unresolved_values,
            "warnings": self.warnings,
        }


def _build_warnings(outcome: ReportOutcome) -> list[str]:

    warnings: list[str] = []

    if outcome.pages_failed:
        warnings.append(
            f"{outcome.pages_failed} page(s) could not be read and are not included below."
        )

    if outcome.pages_skipped:
        warnings.append(
            f"{outcome.pages_skipped} page(s) contained no recognisable laboratory section."
        )

    if outcome.unresolved_values:
        warnings.append(
            f"{outcome.unresolved_values} value(s) could not be interpreted and are marked "
            "'Unknown' - please confirm them with your clinician."
        )

    return warnings


def report_agent(file_path: str, session_id: str, owner: str = ANONYMOUS) -> dict:

    pages = extract_report_pages(file_path)

    outcome = ReportOutcome(pages_total=len(pages))

    # Raises when no page yielded any text, so an unreadable file is
    # reported rather than indexed as nothing.
    report_id = ingest_report(pages)

    session_manager.save_report(session_id, report_id, owner=owner)

    analyses: list[dict] = []

    for page in pages:

        page_text = page.get("text") or ""
        page_number = page.get("page")

        if not page_text.strip():
            outcome.pages_skipped += 1
            continue

        if detect_report_type(page_text) is None:
            logger.info("No recognisable report section on page", extra={"page": page_number})
            outcome.pages_skipped += 1
            continue

        try:
            extracted = extract_structured_report(page_text)
            analyzed = analyze_report(extracted)

        except ExtractionFailed:
            logger.warning("Extraction failed for page", extra={"page": page_number})
            outcome.pages_failed += 1
            continue

        except Exception:
            logger.exception("Unexpected error analysing page", extra={"page": page_number})
            outcome.pages_failed += 1
            continue

        if not analyzed.get("parameters"):
            outcome.pages_skipped += 1
            continue

        outcome.unresolved_values += analyzed.get("unresolved_count", 0)
        outcome.pages_analyzed += 1
        analyses.append(analyzed)

    outcome.warnings = _build_warnings(outcome)

    if not analyses:
        # Never ask the model to summarise nothing.
        logger.warning(
            "No laboratory values extracted from upload",
            extra={"pages_total": outcome.pages_total, "pages_failed": outcome.pages_failed},
        )

        session_manager.save_report_data(session_id, [], NO_VALUES_MESSAGE, owner=owner)

        return {
            "report_id": report_id,
            "analysis": [],
            "summary": NO_VALUES_MESSAGE,
            "outcome": outcome.as_dict(),
        }

    summary = generate_summary(analyses, warnings=outcome.warnings)

    session_manager.save_report_data(session_id, analyses, summary, owner=owner)

    logger.info("Report processed", extra=outcome.as_dict())

    return {
        "report_id": report_id,
        "analysis": analyses,
        "summary": summary,
        "outcome": outcome.as_dict(),
    }
