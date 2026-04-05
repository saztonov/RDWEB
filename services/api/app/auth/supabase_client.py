"""Singleton Supabase client (service_role, обходит RLS).

Инициализируется в lifespan FastAPI, используется во всех слоях backend.
"""

from __future__ import annotations

from supabase import Client, create_client

_client: Client | None = None


def init_supabase(url: str, key: str) -> None:
    """Создать Supabase client при старте сервера."""
    global _client  # noqa: PLW0603
    _client = create_client(url, key)


def get_supabase() -> Client:
    """Получить инициализированный Supabase client."""
    if _client is None:
        raise RuntimeError("Supabase client не инициализирован. Вызовите init_supabase() в lifespan.")
    return _client
