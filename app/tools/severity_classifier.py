from langchain_core.output_parsers import JsonOutputParser
from app.llm.model import safe_invoke

from app.prompts.severity_prompt import SEVERITY_PROMPT
from app.models.severity_model import SeverityOutput


parser = JsonOutputParser(
    pydantic_object=SeverityOutput
)


def classify_severity(query: str):

    prompt = SEVERITY_PROMPT.format(
        query=query
    )

    prompt += f"\n\n{parser.get_format_instructions()}"

    response = safe_invoke(prompt)

    result = parser.parse(
        response.content
    )

    return result