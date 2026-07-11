from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FastEmbedEmbeddings

embedding_model = FastEmbedEmbeddings(
    model_name="BAAI/bge-small-en-v1.5"
)

vectorstore = FAISS.load_local(
    "vectorstore",
    embedding_model,
    allow_dangerous_deserialization=True
)

medical_retriever = vectorstore.as_retriever(
    search_kwargs={"k": 3}
)