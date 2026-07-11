import os

from langchain_community.vectorstores import FAISS

from app.rag.retriever import embedding_model


def get_report_retriever(report_id: str):
    """
    Load the retriever for a specific uploaded report.
    """

    vectorstore_path = os.path.join(
        "report_vectorstore",
        report_id
    )

    vectorstore = FAISS.load_local(
        vectorstore_path,
        embedding_model,
        allow_dangerous_deserialization=True
    )

    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 4}
    )

    return retriever