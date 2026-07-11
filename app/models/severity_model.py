from pydantic import BaseModel
from typing import List


class SeverityOutput(BaseModel):
    severity: int
    risk_level: str
    emergency: bool
    specialist: str
    possible_conditions: List[str]
    reasoning: str