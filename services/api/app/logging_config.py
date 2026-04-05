"""Конфигурация логирования (адаптация из legacy logging_config.py).

Поддерживает два формата: JSON (для production) и human-readable (для dev).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Структурированный JSON-формат для production логов."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = self.formatException(record.exc_info)
        # Дополнительные поля из extra
        for key in ("event", "config", "method", "path", "status_code", "duration_ms", "client_ip"):
            value = getattr(record, key, None)
            if value is not None:
                log_data[key] = value
        return json.dumps(log_data, ensure_ascii=False, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Читаемый формат для локальной разработки."""

    FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    def __init__(self) -> None:
        super().__init__(fmt=self.FORMAT, datefmt="%H:%M:%S")


def setup_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Инициализация логирования.

    Args:
        level: уровень логирования (DEBUG, INFO, WARNING, ERROR)
        fmt: формат вывода ("json" для production, "text" для dev)
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Очищаем существующие handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())

    root.addHandler(handler)

    # Приглушаем шумные библиотеки
    for name in ("httpcore", "httpx", "urllib3", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
