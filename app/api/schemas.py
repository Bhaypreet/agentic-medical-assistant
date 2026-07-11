from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: str
    location: str = ""


class ChatResponse(BaseModel):
    response: str


class SymptomRequest(BaseModel):
    query: str
    location: str
    session_id: str


class UploadResponse(BaseModel):
    report_id: str
    message: str


class ReportChatRequest(BaseModel):
    session_id: str
    question: str