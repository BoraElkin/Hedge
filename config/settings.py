from __future__ import annotations

import functools

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AI providers
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Market data
    alpha_vantage_api_key: str = ""
    polygon_api_key: str = ""
    finnhub_api_key: str = ""

    # Broker
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # General
    log_level: str = "INFO"
    environment: str = "development"

    # AI model defaults
    default_llm_provider: str = "anthropic"  # "anthropic" or "openai"
    default_model: str = "claude-sonnet-4-20250514"

    # Trading defaults
    max_position_pct: float = 0.10  # Max 10% of portfolio in a single position
    max_portfolio_risk: float = 0.02  # Max 2% portfolio risk per trade
    default_universe: list[str] = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
        "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA",
    ]


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
