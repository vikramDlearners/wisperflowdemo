from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./carecircle_dev.db"
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
    elevenlabs_voice_id: Optional[str] = None

    intent_mode: str = "offline_rules"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
