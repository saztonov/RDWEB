"""Подключение к legacy и target PostgreSQL через psycopg2.

Используем psycopg2 напрямую для полноценных транзакций (BEGIN/COMMIT/ROLLBACK).
Supabase SDK не поддерживает транзакции — для batch import это критично.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Generator, Optional

import psycopg2
import psycopg2.extras

from .config import MigrationConfig


class DatabaseClient:
    """Обёртка над psycopg2 для удобной работы с транзакциями."""

    def __init__(self, db_url: str, name: str = "db"):
        self._db_url = db_url
        self._name = name
        self._conn: Optional[psycopg2.extensions.connection] = None

    def connect(self) -> None:
        """Установить подключение."""
        self._conn = psycopg2.connect(self._db_url)
        self._conn.autocommit = False

    def close(self) -> None:
        """Закрыть подключение."""
        if self._conn and not self._conn.closed:
            self._conn.close()

    @property
    def conn(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            raise RuntimeError(f"[{self._name}] Подключение не установлено. Вызовите connect() сначала.")
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[psycopg2.extensions.cursor, None, None]:
        """Контекст-менеджер для атомарной транзакции.

        При ошибке — автоматический ROLLBACK.
        При успехе — COMMIT.
        """
        cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cursor
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            cursor.close()

    def execute(self, query: str, params: Any = None) -> list[dict]:
        """Выполнить SELECT и вернуть результаты."""
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            return []

    def execute_one(self, query: str, params: Any = None) -> Optional[dict]:
        """Выполнить SELECT и вернуть одну строку."""
        rows = self.execute(query, params)
        return rows[0] if rows else None


def create_clients(config: MigrationConfig) -> tuple[DatabaseClient, DatabaseClient]:
    """Создать и подключить клиенты к legacy и target БД."""
    legacy = DatabaseClient(config.legacy_db_url, name="legacy")
    target = DatabaseClient(config.target_db_url, name="target")

    legacy.connect()
    target.connect()

    return legacy, target
