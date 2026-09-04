import uuid

from app.config import settings
from app.logging_config import get_logger
from app.rag.retriever import get_embedding_model

logger = get_logger(__name__)


def ingest_report(pages) -> str:
    """Index one uploaded report and return its id.

    Raises ValueError when no page yielded any text, so the caller can
    tell the patient the file could not be read instead of building an
    empty index and summarising nothing.
    """

    from langchain_community.vectorstores import FAISS
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    texts = [page["text"] for page in pages if (page.get("text") or "").strip()]

    if not texts:
        raise ValueError("No readable text was extracted from this file.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=100,
    )

    chunks = splitter.create_documents(texts)

    if not chunks:
        raise ValueError("No readable text was extracted from this file.")

    store = FAISS.from_documents(chunks, get_embedding_model())

    report_id = str(uuid.uuid4())
    save_path = settings.report_vectorstore_dir / report_id

    store.save_local(str(save_path))

    logger.info(
        "Indexed uploaded report",
        extra={"report_id": report_id, "pages": len(texts), "chunks": len(chunks)},
    )

    return report_id
