"""Single source of configuration for the whole service.

Every knob that used to be a hardcoded literal or a scattered os.getenv()
call lives here. Settings are read once at import; a missing required
value aborts startup with a clear message instead of letting the app boot
"healthy" and fail on the first user request.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -------------------------------------------------- environment

    environment: Literal["development", "staging", "production"] = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    # -------------------------------------------------- credentials

    groq_api_key: str = Field(
        ...,
        description="Groq API key. Required - the service cannot start without it.",
    )

    # Comma-separated machine keys accepted on the X-API-Key header. These
    # are for service-to-service callers, not people - a human signs in
    # with a username and password and gets a bearer token instead.
    api_keys: str = ""

    @property
    def allowed_api_keys(self) -> set[str]:
        return {key.strip() for key in self.api_keys.split(",") if key.strip()}

    # -------------------------------------------------- accounts

    # Server-side pepper mixed into every password hash and used to derive
    # token lookup hashes. Rotating it invalidates all passwords and
    # sessions, so treat it as permanent for a deployment.
    secret_key: str = ""

    auth_token_ttl_hours: int = 24 * 14
    min_password_length: int = 10
    max_password_length: int = 128
    allow_registration: bool = True
    login_rate_limit: str = "10/minute"

    @field_validator("secret_key")
    @classmethod
    def _production_requires_a_secret(cls, value: str, info) -> str:
        if info.data.get("environment") == "production" and len(value.strip()) < 32:
            raise ValueError(
                "SECRET_KEY must be set to at least 32 characters in production - "
                "it is the pepper for every stored password hash."
            )
        return value

    # -------------------------------------------------- model

    groq_model: str = "openai/gpt-oss-20b"
    groq_temperature: float = 0.2
    groq_timeout_seconds: float = 60.0
    groq_max_retries: int = 4
    groq_transcription_model: str = "whisper-large-v3-turbo"

    # -------------------------------------------------- http

    allowed_origins: str = "http://localhost:8501,http://127.0.0.1:8501"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    chat_rate_limit: str = "20/minute"
    upload_rate_limit: str = "5/minute"
    transcribe_rate_limit: str = "10/minute"

    # -------------------------------------------------- storage

    database_url: str = "sqlite:///./sessions.db"

    upload_dir: Path = Path("uploads")
    vectorstore_dir: Path = Path("vectorstore")
    report_vectorstore_dir: Path = Path("report_vectorstore")
    data_dir: Path = Path("data")

    # -------------------------------------------------- limits

    max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB
    max_report_pages: int = 25
    max_history_messages: int = 20
    report_retention_hours: int = 24
    pending_state_ttl_seconds: int = 30 * 60

    # -------------------------------------------------- retrieval

    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    chunk_size: int = 500
    chunk_overlap: int = 50
    retriever_k: int = 3
    report_retriever_k: int = 4

    # -------------------------------------------------- observability

    log_level: str = "INFO"
    sentry_dsn: str = ""

    # Prints the raw OCR text and raw model extraction output. This is
    # patient data, so it must never be enabled in production - the
    # validator below enforces that.
    debug_log_report_content: bool = False

    @field_validator("debug_log_report_content")
    @classmethod
    def _no_phi_logging_in_production(cls, value: bool, info) -> bool:
        if value and info.data.get("environment") == "production":
            raise ValueError(
                "debug_log_report_content cannot be enabled in production - "
                "it writes patient report content to stdout."
            )
        return value

    # API_KEYS is no longer required in production. Every data endpoint
    # now demands a signed-in user or a machine key unconditionally, so
    # there is no configuration that leaves the service open.


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor so the environment is parsed exactly once.

    A misconfiguration aborts startup with the offending variables named,
    rather than a pydantic traceback the operator has to decode.
    """

    try:
        return Settings()
    except ValidationError as error:
        problems = "\n".join(
            f"  - {'.'.join(str(part) for part in item['loc']).upper()}: {item['msg']}"
            for item in error.errors()
        )

        raise SystemExit(
            "Cannot start: the environment is not configured correctly.\n\n"
            f"{problems}\n\n"
            "See .env.example for the full list of variables."
        ) from error


settings = get_settings()
