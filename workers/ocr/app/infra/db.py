"""Supabase client singleton для worker context.

Использует service_role key для обхода RLS (worker не имеет auth.uid()).
Паттерн аналогичен workers/ocr/app/jobs/model_sync.py::_get_supabase().
"""

from __future__ import annotations

import logging

from supabase import Client, create_client

from ..config import get_worker_settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_db() -> Client:
    """Получить Supabase client с service_role key."""
    global _client
    if _client is None:
        settings = get_worker_settings()
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError("SUPABASE_URL и SUPABASE_KEY обязательны для OCR worker")
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client инициализирован для worker")
    return _client


def reset_client() -> None:
    """Сбросить клиент — для тестов."""
    global _client
    _client = None
