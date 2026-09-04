from app.llm.model import safe_invoke
from app.logging_config import get_logger

logger = get_logger(__name__)

SUMMARY_PROMPT = """
You are an experienced physician explaining a laboratory report to the patient
who owns it.

Analysed laboratory report:

{report}

{warnings}

Write the summary in exactly this structure:

Overall Summary:
- ...

Abnormal Findings:
- ...

Values We Could Not Read:
- ...

Recommendations:
- ...

Lifestyle Advice:
- ...

When To Seek Care:
- ...

Rules:
- Use plain language a non-medical reader understands.
- Only describe values that appear in the data above. Never invent a test,
  a number or a reference range.
- A value with status "Unknown" could NOT be interpreted. List those under
  "Values We Could Not Read" and say they need confirming with a clinician.
  Never describe an Unknown value as normal.
- If there are no abnormal findings, say so plainly rather than padding.
- If a finding needs urgent attention, say so explicitly under
  "When To Seek Care".
- Do not state a diagnosis as fact.
"""


def generate_summary(report_analysis: list, warnings: list[str] | None = None) -> str:
    """Summarise analysed report sections.

    Callers must not pass an empty list - summarising nothing produced a
    confident report about data the model had never seen.
    """

    if not report_analysis:
        raise ValueError("generate_summary requires at least one analysed report section.")

    warning_block = ""

    if warnings:
        warning_block = "Processing notes to mention honestly in the summary:\n" + "\n".join(
            f"- {warning}" for warning in warnings
        )

    prompt = SUMMARY_PROMPT.format(report=report_analysis, warnings=warning_block)

    logger.info("Generating report summary", extra={"sections": len(report_analysis)})

    return safe_invoke(prompt).content
