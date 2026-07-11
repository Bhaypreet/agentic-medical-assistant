import time

from app.agents.summary_agent import generate_summary
from app.report.parser import extract_report_pages
from app.report.extractor import extract_report_information, clean_json_response
from app.report.analyzer import analyze_report
from app.report.section_detector import detect_report_type

from app.report_rag.ingest import ingest_report
from app.session.session_manager import session_manager


def report_agent(file_path: str, session_id: str):
    """
    Complete Report Processing Pipeline (works for PDF reports and
    photographed/scanned image reports alike).
    """

    pages = extract_report_pages(file_path)

    report_id = ingest_report(pages)

    session_manager.save_report(session_id, report_id)

    all_reports = []

    for page in pages:

        page_text = page["text"]

        report_type = detect_report_type(page_text)

        if report_type is None:
            print(f"Skipping Page {page['page']} (No Report Found)")
            continue

        print(f"\nProcessing Page {page['page']} -> {report_type}")

        try:
            report = extract_report_information(page_text)
            report = clean_json_response(report)
            analyzed_report = analyze_report(report)
            all_reports.append(analyzed_report)

        except Exception as e:
            print(f"Error processing Page {page['page']}: {e}")

        time.sleep(1)

    summary = generate_summary(all_reports)

    session_manager.save_report_data(session_id, all_reports, summary)

    return {
        "report_id": report_id,
        "analysis": all_reports,
        "summary": summary
    }