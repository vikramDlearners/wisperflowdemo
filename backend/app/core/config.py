from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./carecircle_dev.db"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg3(cls, value: str) -> str:
        """The installed PostgreSQL driver is psycopg (v3); psycopg2 is not a dependency. Read postgresql://,
        postgres:// and postgresql+psycopg2:// URLs with psycopg."""
        for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value
    secret_key: str = "dev-only-change-me"
    login_link_base_url: str = "http://localhost:5173/auth/verify"
    parent_invite_base_url: str = "http://localhost:5173/parent/accept-invite"
    parent_invite_hours: int = 72
    session_days: int = 30
    login_token_minutes: int = 15
    otp_minutes: int = 10
    dev_fixed_otp: Optional[str] = "123456"


    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None

    sms_provider: str = "mock"

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    elevenlabs_api_key: Optional[str] = None
    elevenlabs_stt_model: str = "scribe_v1"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    # Per-language TTS model overrides, "code:model" pairs separated by commas. Telugu, Malayalam and Kannada
    # are not supported by multilingual v2, so they default to eleven_v3; other languages use elevenlabs_tts_model.
    elevenlabs_tts_model_by_language: str = "te:eleven_v3,ml:eleven_v3,kn:eleven_v3"
    elevenlabs_voice_id: Optional[str] = None

    intent_mode: str = "offline_rules"

    # Background jobs (missed-dose alerts, daily summaries). Tests turn this off.
    scheduler_enabled: bool = True
    # Shown on the parent's emergency pop-up (tap to call). A dummy number until a real one is set in .env.
    emergency_number: str = "+91 00000 00000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
