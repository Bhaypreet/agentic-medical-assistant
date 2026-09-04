from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(min_length=1, max_length=64)
    location: str = Field(default="", max_length=200)


class ChatResponse(BaseModel):
    response: str
    suggestions: list[str] = Field(default_factory=list)
    session_id: str


class MessageOut(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageOut]


class SessionSummary(BaseModel):
    id: str
    chat_name: str
    has_report: bool
    updated_at: str | None = None


class UploadAccepted(BaseModel):
    job_id: str
    session_id: str
    status: str


class JobStatus(BaseModel):
    job_id: str
    session_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    filename: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None


class TranscriptionResponse(BaseModel):
    text: str


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


# ------------------------------------------------------------------ auth


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: str
    username: str
    display_name: str


class MeResponse(BaseModel):
    username: str
    display_name: str
    is_service_account: bool
