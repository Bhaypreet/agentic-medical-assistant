from app.api.security import validate_report_id
from app.config import settings
from app.logging_config import get_logger
from app.rag.retriever import get_embedding_model

logger = get_logger(__name__)


class ReportStoreMissing(RuntimeError):
    """No vector store exists for this report id."""


def get_report_retriever(report_id: str):
    """Load the retriever for one uploaded report.

    FAISS.load_local unpickles, so the path must never be attacker
    controlled. report_id is therefore required to parse as a UUID, and
    the resolved path is confirmed to sit inside the report store root -
    previously it was joined straight into the path with no validation, so
    a tampered session record could point the loader anywhere on disk.
    """

    safe_id = validate_report_id(report_id)

    root = settings.report_vectorstore_dir.resolve()
    path = (root / safe_id).resolve()

    if root not in path.parents:
        raise ValueError("Resolved report path escaped the report store root.")

    if not path.exists():
        raise ReportStoreMissing(f"No stored report for id {safe_id}.")

    from langchain_community.vectorstores import FAISS

    store = FAISS.load_local(
        str(path),
        get_embedding_model(),
        allow_dangerous_deserialization=True,
    )

    return store.as_retriever(search_kwargs={"k": settings.report_retriever_k})
