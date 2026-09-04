from pydantic import BaseModel, Field, field_validator


class SeverityOutput(BaseModel):
    """Triage result. Bounds are enforced here so a nonsensical model
    response is caught rather than routed on."""

    severity: int = Field(ge=1, le=5)
    risk_level: str
    emergency: bool = False
    specialist: str = "General Physician"
    possible_conditions: list[str] = Field(default_factory=list)
    reasoning: str = ""

    @field_validator("possible_conditions", mode="before")
    @classmethod
    def _coerce_conditions(cls, value):
        """Models sometimes return a single string rather than a list."""

        if value is None:
            return []

        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]

        return value

    @field_validator("specialist")
    @classmethod
    def _default_specialist(cls, value: str) -> str:
        return value.strip() or "General Physician"
