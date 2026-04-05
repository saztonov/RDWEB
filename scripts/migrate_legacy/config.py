"""Конфигурация migration utility.

Все параметры подключения берутся из CLI-аргументов или env переменных.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MigrationConfig:
    """Конфигурация одного прогона миграции."""

    # Подключение к legacy БД (Supabase PostgreSQL)
    legacy_db_url: str

    # Подключение к целевой БД (новый Supabase PostgreSQL)
    target_db_url: str

    # Целевой workspace UUID
    workspace_id: str

    # UUID document_profile (для привязки промптов и документов)
    document_profile_id: Optional[str] = None

    # Маппинг legacy engine → target ocr_source UUID
    # Формат: {"openrouter": "<uuid>", "datalab": "<uuid>", "chandra": "<uuid>"}
    engine_source_map: dict[str, str] = field(default_factory=dict)

    # UUID пользователя-инициатора миграции (для created_by / initiated_by)
    migrator_user_id: Optional[str] = None

    # Режим работы
    dry_run: bool = False
    skip_existing: bool = True
    verbose: bool = False

    # Путь к state файлу (маппинг legacy_node_id → new_document_id)
    state_file: str = "scripts/migrate_legacy/.migration_state.json"

    @classmethod
    def from_env(cls, **overrides) -> MigrationConfig:
        """Создать конфигурацию из env переменных + overrides из CLI."""
        defaults = {
            "legacy_db_url": os.environ.get("LEGACY_DATABASE_URL", ""),
            "target_db_url": os.environ.get("TARGET_DATABASE_URL", ""),
            "workspace_id": os.environ.get("MIGRATION_WORKSPACE_ID", ""),
            "document_profile_id": os.environ.get("MIGRATION_PROFILE_ID"),
            "migrator_user_id": os.environ.get("MIGRATION_USER_ID"),
        }

        # Парсинг engine_source_map из env: "openrouter=uuid1,chandra=uuid2"
        engine_map_raw = os.environ.get("MIGRATION_ENGINE_MAP", "")
        engine_map = {}
        if engine_map_raw:
            for pair in engine_map_raw.split(","):
                if "=" in pair:
                    k, v = pair.strip().split("=", 1)
                    engine_map[k.strip()] = v.strip()
        defaults["engine_source_map"] = engine_map

        defaults.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**defaults)
