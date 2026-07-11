import os
from dotenv import load_dotenv

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

# Load environment variables
load_dotenv()

DATA_DIR = "data"
VECTORSTORE_DIR = "vectorstore"

# -----------------------------
# Load Documents
# -----------------------------
documents = []

for file in os.listdir(DATA_DIR):
    if file.endswith(".txt"):
        path = os.path.join(DATA_DIR, file)

        loader = TextLoader(path, encoding="utf-8")
        docs = loader.load()

        documents.extend(docs)

        print(f"Loaded: {file}")

print(f"\nTotal documents loaded: {len(documents)}")

# -----------------------------
# Split Documents into Chunks
# -----------------------------
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

chunks = text_splitter.split_documents(documents)

print(f"\nTotal chunks created: {len(chunks)}")

# -----------------------------
# Create Embeddings
# -----------------------------
print("\nLoading embedding model...")

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# -----------------------------
# Create FAISS Vector Store
# -----------------------------
print("\nCreating FAISS vector database...")

vectorstore = FAISS.from_documents(
    documents=chunks,
    embedding=embeddings
)

# -----------------------------
# Save Vector Store
# -----------------------------
vectorstore.save_local(VECTORSTORE_DIR)

print(f"\nVector database saved to '{VECTORSTORE_DIR}'")

# -----------------------------
# Preview
# -----------------------------
print("\nFirst Chunk Preview:\n")
print(chunks[0].page_content[:500])