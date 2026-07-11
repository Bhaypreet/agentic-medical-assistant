from langchain_core.prompts import ChatPromptTemplate

from app.llm.model import safe_invoke
from app.report_rag.retriever import get_report_retriever


prompt = ChatPromptTemplate.from_template("""
You are a friendly, conversational medical assistant chatting with a patient about their
uploaded lab report - like ChatGPT, but with access to their personal data.

Previous conversation:
{history}

Structured, already-verified data extracted from the patient's report (this is your
primary and most reliable source - always prefer this over the raw excerpts below):
{structured_data}

Raw excerpts from the report (secondary/supplementary source, may be incomplete or
out of order - use only if the structured data above doesn't cover the question):
{raw_context}

FORMATTING RULES (important):
- NEVER answer in one long paragraph.
- Use markdown: short headers, bullet points, numbered steps, or a table wherever it fits
  (tables are great for lab values: Test | Result | Normal Range | Meaning).
- Keep each bullet/line short and scannable.
- Bold key values and abnormal findings.
                                    
LANGUAGE RULE:
- Respond in the SAME language the patient's question is written in.

Instructions:
- Answer directly and specifically using the structured data whenever it's relevant.
- If the question is a general health question not covered by either source,
  answer using your own general medical knowledge instead of refusing.
- Do not say things like "I don't see numerical values" if the structured data
  above actually contains them - always check structured data first.

Question:
{question}

Answer:
""")


def chat_with_report(report_id: str, question: str, structured_data=None, chat_history=None):

    retriever = get_report_retriever(report_id)
    docs = retriever.invoke(question)
    raw_context = "\n\n".join(doc.page_content for doc in docs)

    structured_text = ""
    if structured_data:
        analysis = structured_data.get("analysis", [])
        summary = structured_data.get("summary", "")
        structured_text = f"Summary:\n{summary}\n\nDetailed Analysis:\n{analysis}"

    history_text = ""
    if chat_history:
        recent = chat_history[-6:]
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in recent)

    formatted_prompt = prompt.format(
        raw_context=raw_context,
        structured_data=structured_text,
        question=question,
        history=history_text
    )

    response = safe_invoke(formatted_prompt)

    return response.content