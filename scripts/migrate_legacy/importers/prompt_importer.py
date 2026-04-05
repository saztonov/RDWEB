"""Импорт промптов из legacy config.yaml → prompt_templates.

Порядок: выполняется первым (промпты не зависят от документов).
"""

from __future__ import annotations

import json
import logging

from ..config import MigrationConfig
from ..db import DatabaseClient
from ..mappers.prompt_mapper import load_config_yaml, map_prompts_from_config
from ..utils import MigrationSummary, console

logger = logging.getLogger("migrate_legacy.prompt_importer")


def import_prompts(
    config: MigrationConfig,
    target_db: DatabaseClient,
    summary: MigrationSummary,
    config_yaml_path: str,
) -> dict[str, str]:
    """Импортировать промпты из legacy config.yaml.

    Returns:
        Маппинг template_key → prompt_template_id для использования в других импортерах.
    """
    console.print("[bold]Импорт промптов из config.yaml...[/bold]")

    yaml_config = load_config_yaml(config_yaml_path)
    prompts = map_prompts_from_config(yaml_config, config.document_profile_id)

    template_map: dict[str, str] = {}

    for prompt_data in prompts:
        template_key = prompt_data["template_key"]

        # Проверка: уже существует?
        if config.skip_existing:
            existing = target_db.execute_one(
                "SELECT id FROM prompt_templates WHERE template_key = %s AND version = %s",
                (template_key, prompt_data["version"]),
            )
            if existing:
                template_map[template_key] = existing["id"]
                summary.prompts_skipped += 1
                logger.info("Промпт %s уже существует — пропускаем", template_key)
                continue

        if config.dry_run:
            console.print(f"  [DRY-RUN] Создали бы промпт: {template_key} ({prompt_data['block_kind']}/{prompt_data['source_type']})")
            summary.prompts_created += 1
            template_map[template_key] = prompt_data["id"]
            continue

        # INSERT
        with target_db.transaction() as cur:
            cur.execute(
                """
                INSERT INTO prompt_templates
                    (id, template_key, version, is_active, document_profile_id,
                     block_kind, source_type, system_template, user_template,
                     parser_strategy, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    prompt_data["id"],
                    template_key,
                    prompt_data["version"],
                    prompt_data["is_active"],
                    prompt_data.get("document_profile_id"),
                    prompt_data["block_kind"],
                    prompt_data["source_type"],
                    prompt_data["system_template"],
                    prompt_data["user_template"],
                    prompt_data["parser_strategy"],
                    prompt_data["notes"],
                ),
            )
            row = cur.fetchone()
            template_map[template_key] = row["id"]

        summary.prompts_created += 1
        logger.info("Создан промпт: %s → %s", template_key, prompt_data["id"])

    console.print(f"  Промптов: создано={summary.prompts_created}, пропущено={summary.prompts_skipped}")
    return template_map
