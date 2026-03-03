"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- App ---
    app_name: str = "Customer Support Voice Agent"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # --- LiveKit ---
    livekit_url: str = "ws://livekit-server:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"

    # --- OpenAI ---
    openai_api_key: str = ""

    # --- Redis ---
    redis_url: str = "redis://redis:6379/0"

    # --- STT Service ---
    stt_service_url: str = "http://stt-service:8001"

    # --- TTS Service ---
    tts_service_url: str = "http://tts-service:8002"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
