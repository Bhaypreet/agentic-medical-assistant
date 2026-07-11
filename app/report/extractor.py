import json
import re

from app.llm.model import safe_invoke

EXTRACTION_PROMPT = """
You are an expert medical report extraction system.

Extract every laboratory parameter from the report below.

Return ONLY valid JSON, with no markdown formatting, in exactly this shape:

{{
    "report_type": "...",
    "parameters": {{
        "Hemoglobin": {{
            "value": "...",
            "unit": "...",
            "reference_range": "...",
            "status": "..."
        }}
    }}
}}

Rules for "status":
- If the report text explicitly states a status/flag/comment for this value
  (e.g. "High", "Low", "Normal", "Borderline", "Deficient", "Elevated",
  arrows like ↑ / ↓, or a Status/Comment column), use that EXACT wording,
  normalized to one of: "High", "Low", "Normal", "Borderline".
- Only if no status is stated anywhere in the source text, leave it as an
  empty string "" - it will be calculated later from the reference range.
- Never guess a status - only report what the text actually says.

Medical Report:

{report}
"""


def extract_report_information(report_text: str):

    prompt = EXTRACTION_PROMPT.format(
        report=report_text
    )

    response = safe_invoke(prompt)

    raw_content = response.content

    # DEBUG: see exactly what the LLM returned, before any cleanup
    print("\n----- RAW LLM EXTRACTION RESPONSE -----")
    print(repr(raw_content)[:1000])
    print("----- END RAW RESPONSE -----\n")

    return raw_content


def clean_json_response(response_text: str):

    if not response_text or not response_text.strip():
        raise ValueError("LLM returned an empty extraction response.")

    response_text = response_text.strip()

    response_text = re.sub(r"^```json\s*", "", response_text)
    response_text = re.sub(r"^```\s*", "", response_text)
    response_text = re.sub(r"\s*```$", "", response_text)

    return json.loads(response_text)