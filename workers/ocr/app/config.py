"""Настройки Celery worker через pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Redis / Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    celery_concurrency: int = 2
    worker_max_tasks_per_child: int = 50
    worker_prefetch: int = 1

    # Timeouts
    task_soft_timeout: int = 3600
    task_hard_timeout: int = 4200
    task_retry_delay: int = 60

    # Priority
    default_task_priority: int = 5

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

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


@lru_cache
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
