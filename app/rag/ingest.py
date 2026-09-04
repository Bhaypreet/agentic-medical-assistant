"""Build the medical knowledge-base vector store.

Run as a script:  python -m app.rag.ingest

This used to execute its entire body at import time, so merely importing
the module rebuilt the index.
"""

import argparse
import sys

from app.config import settings
from app.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


def build_vectorstore(rebuild: bool = False) -> int:
    """Ingest data/*.txt into a FAISS index. Returns the chunk count."""

    from langchain_community.document_loaders import TextLoader
    from langchain_community.vectorstores import FAISS
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    from app.rag.retriever import get_embedding_model

    if settings.vectorstore_dir.exists() and not rebuild:
        logger.info(
            "Vector store already exists; pass --rebuild to recreate it",
            extra={"path": str(settings.vectorstore_dir)},
        )
        return 0

    source_files = sorted(settings.data_dir.glob("*.txt"))

    if not source_files:
        raise SystemExit(f"No .txt source files found in {settings.data_dir}/")

    documents = []

    for path in source_files:
        documents.extend(TextLoader(str(path), encoding="utf-8").load())
        logger.info("Loaded source document", extra={"file": path.name})

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    chunks = splitter.split_documents(documents)

    logger.info(
        "Split documents into chunks",
        extra={"documents": len(documents), "chunks": len(chunks)},
    )

    store = FAISS.from_documents(documents=chunks, embedding=get_embedding_model())
    store.save_local(str(settings.vectorstore_dir))

    logger.info(
        "Vector store written",
        extra={"path": str(settings.vectorstore_dir), "chunks": len(chunks)},
    )

    return len(chunks)


def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(description="Build the medical knowledge base.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recreate the index even if one already exists.",
    )

    args = parser.parse_args(argv)

    configure_logging()
    build_vectorstore(rebuild=args.rebuild)

    return 0


if __name__ == "__main__":
    sys.exit(main())
