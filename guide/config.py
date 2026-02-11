"""Configuration for Guide."""

from __future__ import annotations

import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""  # Gemini API key

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    environment: str = "development"

    # AI Models
    default_model: str = "claude-sonnet-4-20250514"  # For guidance/reasoning
    vision_model: str = "gemini-2.0-flash"  # For vision analysis (cheaper, faster)
    vision_provider: str = "gemini"  # "gemini" or "claude"

    # Session limits
    max_images_per_session: int = 100
    session_timeout_minutes: int = 60


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
