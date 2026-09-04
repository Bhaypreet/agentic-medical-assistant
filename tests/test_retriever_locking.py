"""Concurrency around the lazily-loaded retrieval singletons.

get_medical_retriever() used to hold one shared lock and then call
get_embedding_model(), which waited on that same non-reentrant lock -
a deadlock that blocked before it logged anything, so the knowledge base
stayed "degraded" forever and every retrieval-backed request hung.

The vector libraries are not installed in CI, so they are stubbed here;
the locking behaviour under test is entirely our own.
"""

import sys
import threading
import types
from unittest.mock import MagicMock

import pytest

from app.rag import retriever


@pytest.fixture
def stub_vector_libs(monkeypatch):
    """Stand in for langchain_community, which CI does not install."""

    faiss = MagicMock()
    store = MagicMock()
    store.as_retriever.return_value = MagicMock(name="retriever")
    faiss.load_local.return_value = store

    vs_mod = types.ModuleType("langchain_community.vectorstores")
    vs_mod.FAISS = faiss

    emb_mod = types.ModuleType("langchain_community.embeddings")
    emb_mod.FastEmbedEmbeddings = MagicMock(name="FastEmbedEmbeddings")

    pkg = types.ModuleType("langchain_community")

    monkeypatch.setitem(sys.modules, "langchain_community", pkg)
    monkeypatch.setitem(sys.modules, "langchain_community.vectorstores", vs_mod)
    monkeypatch.setitem(sys.modules, "langchain_community.embeddings", emb_mod)

    monkeypatch.setattr(retriever, "_embedding_model", None)
    monkeypatch.setattr(retriever, "_retriever", None)

    yield faiss

    retriever._embedding_model = None
    retriever._retriever = None


def test_retriever_load_does_not_deadlock(tmp_path, monkeypatch, stub_vector_libs):
    monkeypatch.setattr(retriever.settings, "vectorstore_dir", tmp_path)

    done = threading.Event()
    result = {}

    def load():
        try:
            result["value"] = retriever.get_medical_retriever()
        except Exception as exc:  # pragma: no cover - failure path
            result["error"] = exc
        finally:
            done.set()

    threading.Thread(target=load, daemon=True).start()

    assert done.wait(timeout=10), "get_medical_retriever deadlocked"
    assert "error" not in result, result.get("error")
    assert result["value"] is not None


def test_concurrent_callers_build_the_retriever_once(tmp_path, monkeypatch, stub_vector_libs):
    monkeypatch.setattr(retriever.settings, "vectorstore_dir", tmp_path)

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(retriever.get_medical_retriever()))
        for _ in range(6)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "a caller deadlocked"

    assert len(results) == 6
    assert len({id(r) for r in results}) == 1
    assert stub_vector_libs.load_local.call_count == 1


def test_warm_up_marks_the_knowledge_base_ready(tmp_path, monkeypatch, stub_vector_libs):
    monkeypatch.setattr(retriever.settings, "vectorstore_dir", tmp_path)

    assert retriever.warm_up() is True
    assert retriever.is_ready() is True


def test_missing_vector_store_raises_rather_than_hanging(tmp_path, monkeypatch):
    monkeypatch.setattr(retriever.settings, "vectorstore_dir", tmp_path / "absent")
    monkeypatch.setattr(retriever, "_retriever", None)

    with pytest.raises(retriever.KnowledgeBaseUnavailable):
        retriever.get_medical_retriever()


def test_warm_up_reports_failure_instead_of_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(retriever.settings, "vectorstore_dir", tmp_path / "absent")
    monkeypatch.setattr(retriever, "_retriever", None)

    assert retriever.warm_up() is False
