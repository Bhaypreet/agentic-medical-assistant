from app.report_rag.chain import chat_with_report

question = input("Ask about the report: ")

answer = chat_with_report(question)

print("\n")

print(answer)
from app.report_rag.ingest import ingest_report

ingest_report(
    "testpdf.pdf"
)