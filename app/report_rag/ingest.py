import os
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from app.rag.retriever import embedding_model


def ingest_report(pages):

    documents = []

    for page in pages:
        documents.append(page["text"])

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100
    )

    chunks = splitter.create_documents(documents)

    vectorstore = FAISS.from_documents(
        chunks,
        embedding_model
    )

    report_id = str(uuid.uuid4())

    save_path = os.path.join(
        "report_vectorstore",
        report_id
    )

    vectorstore.save_local(save_path)

    return report_id