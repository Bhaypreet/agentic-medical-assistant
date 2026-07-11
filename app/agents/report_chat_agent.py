from app.session.session_manager import session_manager
from app.report_rag.chain import chat_with_report


def report_chat_agent(session_id: str, question: str, chat_history=None):

    report_id = session_manager.get_report(session_id)

    if report_id is None:
        return "No medical report has been uploaded yet."

    report_data = session_manager.get_report_data(session_id)

    answer = chat_with_report(
        report_id=report_id,
        question=question,
        structured_data=report_data,
        chat_history=chat_history
    )

    return answer