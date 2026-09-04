"""Lazy access to the medical knowledge base.

The embedding model and FAISS index used to load at module import, so a
missing vectorstore/ directory made the entire application fail to import
and the container restart-loop instead of serving a degraded response.
Both are now built on first use, and a failure is reported rather than
raised through the import machinery.
"""

import threading

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_embedding_model = None
_retriever = None


class KnowledgeBaseUnavailable(RuntimeError):
    """The knowledge base could not be loaded."""


def get_embedding_model():
    """The embedding model, shared by the knowledge base and report stores."""

    global _embedding_model

    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                from langchain_community.embeddings import FastEmbedEmbeddings

                logger.info(
                    "Loading embedding model",
                    extra={"model": settings.embedding_model_name},
                )
                _embedding_model = FastEmbedEmbeddings(model_name=settings.embedding_model_name)

    return _embedding_model


def get_medical_retriever():

    global _retriever

    if _retriever is None:
        with _lock:
            if _retriever is None:
                path = settings.vectorstore_dir

                # Checked before the import so a missing store fails fast
                # instead of paying to load the vector libraries first.
                if not path.exists():
                    raise KnowledgeBaseUnavailable(
                        f"No vector store at {path}. Run 'python -m app.rag.ingest' first."
                    )

                from langchain_community.vectorstores import FAISS

                # The index is built by our own ingest step and never
                # accepted from a user, so unpickling it is safe here.
                store = FAISS.load_local(
                    str(path),
                    get_embedding_model(),
                    allow_dangerous_deserialization=True,
                )

                _retriever = store.as_retriever(search_kwargs={"k": settings.retriever_k})
                logger.info("Knowledge base loaded", extra={"path": str(path)})

    return _retriever


def warm_up() -> bool:
    """Load retrieval at startup. Returns False instead of raising."""

    try:
        get_medical_retriever()
        return True
    except Exception:
        logger.exception("Knowledge base failed to load")
        return False


def is_ready() -> bool:
    return _retriever is not None
