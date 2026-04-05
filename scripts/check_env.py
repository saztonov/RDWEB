#!/usr/bin/env python3
"""Валидация .env файла — проверяет наличие обязательных переменных.

Использование:
    python scripts/check_env.py              # проверить .env
    python scripts/check_env.py path/to/.env # проверить конкретный файл
"""

from __future__ import annotations

import sys
from pathlib import Path

# Обязательные переменные по группам
REQUIRED_VARS: dict[str, list[str]] = {
    "Backend": [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "REDIS_URL",
    ],
    "Worker": [
        "CELERY_BROKER_URL",
    ],
}

# Рекомендуемые (предупреждение, но не ошибка)
RECOMMENDED_VARS: dict[str, list[str]] = {
    "OCR Providers": [
        "OPENROUTER_API_KEY",
    ],
    "R2 Storage": [
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ],
}


def parse_env(path: Path) -> dict[str, str]:
    """Парсинг .env файла в dict."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".env")

    if not env_path.exists():
        print(f"ОШИБКА: файл {env_path} не найден")
        print(f"  Скопируйте .env.example: cp .env.example {env_path}")
        return 1

    env = parse_env(env_path)
    errors: list[str] = []
    warnings: list[str] = []

    for group, vars_ in REQUIRED_VARS.items():
        for var in vars_:
            if not env.get(var):
                errors.append(f"  [{group}] {var} — не задана или пуста")

    for group, vars_ in RECOMMENDED_VARS.items():
        for var in vars_:
            if not env.get(var):
                warnings.append(f"  [{group}] {var} — не задана (рекомендуется)")

    if errors:
        print("ОШИБКИ (обязательные переменные):")
        print("\n".join(errors))

    if warnings:
        print("\nПРЕДУПРЕЖДЕНИЯ (рекомендуемые):")
        print("\n".join(warnings))

    if not errors and not warnings:
        print(f"OK: все переменные в {env_path} заданы")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
