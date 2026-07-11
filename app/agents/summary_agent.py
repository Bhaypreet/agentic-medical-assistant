from app.llm.model import safe_invoke


SUMMARY_PROMPT = """
You are an experienced physician.

Below is the analyzed laboratory report.

{report}

Write a professional report in this format.

Overall Summary:
- ...

Abnormal Findings:
- ...

Recommendations:
- ...

Lifestyle Advice:
- ...

Emergency Warning:
- ...

Keep the language easy for normal people.
"""


def generate_summary(report_analysis):

    prompt = SUMMARY_PROMPT.format(
        report=report_analysis
    )

    response = safe_invoke(prompt)

    return response.content