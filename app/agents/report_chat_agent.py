from app.report_rag.chain import chat_with_report
from app.session.session_manager import ANONYMOUS, session_manager

NO_REPORT = (
    "You haven't uploaded a report yet. Use the 📎 button to upload a PDF or a "
    "photo of your lab report, and I'll walk you through it."
)


def report_chat_agent(
    session_id: str,
    question: str,
    chat_history=None,
    owner: str = ANONYMOUS,
) -> str:

    report_id = session_manager.get_report(session_id, owner=owner)

    if report_id is None:
        return NO_REPORT

    return chat_with_report(
        report_id=report_id,
        question=question,
        structured_data=session_manager.get_report_data(session_id, owner=owner),
        chat_history=chat_history,
    )
