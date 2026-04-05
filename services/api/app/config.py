"""Настройки FastAPI сервера через pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""

    # OCR providers
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai"
    datalab_api_key: str = ""
    chandra_base_url: str = ""

    # API
    api_secret_key: str = "change-me"

    # Logging
    log_level: str = "INFO"
    log_format: str = "text"


@lru_cache
def get_settings() -> Settings:
    return Settings()
