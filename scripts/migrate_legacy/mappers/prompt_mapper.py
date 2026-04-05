"""Маппинг legacy промптов → prompt_templates rows.

Источники:
1. config.yaml — openrouter_image_system_prompt/user_prompt, openrouter_stamp_system_prompt/user_prompt
2. build_strip_prompt (single block fallback) — для text/openrouter

Все legacy промпты создаются с is_active=false, notes="Импорт из legacy config.yaml".
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import yaml

from ..utils import new_uuid

logger = logging.getLogger("migrate_legacy.prompt_mapper")

# Маппинг ключей config.yaml → prompt_templates
_CONFIG_PROMPT_MAP = [
    {
        "system_key": "openrouter_image_system_prompt",
        "user_key": "openrouter_image_user_prompt",
        "template_key": "legacy_image_openrouter",
        "block_kind": "image",
        "source_type": "openrouter",
        "parser_strategy": "json_schema",
    },
    {
        "system_key": "openrouter_stamp_system_prompt",
        "user_key": "openrouter_stamp_user_prompt",
        "template_key": "legacy_stamp_openrouter",
        "block_kind": "stamp",
        "source_type": "openrouter",
        "parser_strategy": "json_schema",
    },
]

# Fallback промпт для text блоков (из build_strip_prompt, single block case)
_TEXT_FALLBACK_PROMPT = {
    "system": "You are an expert OCR system. Extract text accurately.",
    "user": "Распознай текст на изображении. Сохрани форматирование.",
}


def load_config_yaml(path: str) -> dict:
    """Загрузить legacy config.yaml."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def map_prompts_from_config(
    config: dict,
    document_profile_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Извлечь промпты из legacy config.yaml → list of prompt_templates INSERT dicts.

    Все промпты создаются с is_active=false.
    """
    prompts: list[dict[str, Any]] = []

    for mapping in _CONFIG_PROMPT_MAP:
        system_text = config.get(mapping["system_key"], "")
        user_text = config.get(mapping["user_key"], "")

        if not system_text and not user_text:
            logger.info("Промпт %s пуст в config.yaml — пропускаем", mapping["template_key"])
            continue

        prompts.append({
            "id": new_uuid(),
            "template_key": mapping["template_key"],
            "version": 1,
            "is_active": False,
            "document_profile_id": document_profile_id,
            "block_kind": mapping["block_kind"],
            "source_type": mapping["source_type"],
            "system_template": system_text,
            "user_template": user_text,
            "parser_strategy": mapping["parser_strategy"],
            "notes": "Импорт из legacy config.yaml",
        })

    # Добавляем fallback промпт для text блоков
    prompts.append({
        "id": new_uuid(),
        "template_key": "legacy_text_openrouter",
        "version": 1,
        "is_active": False,
        "document_profile_id": document_profile_id,
        "block_kind": "text",
        "source_type": "openrouter",
        "system_template": _TEXT_FALLBACK_PROMPT["system"],
        "user_template": _TEXT_FALLBACK_PROMPT["user"],
        "parser_strategy": "plain_text",
        "notes": "Импорт из legacy build_strip_prompt (single block fallback)",
    })

    # Добавляем lmstudio-версии промптов для text
    prompts.append({
        "id": new_uuid(),
        "template_key": "legacy_text_lmstudio",
        "version": 1,
        "is_active": False,
        "document_profile_id": document_profile_id,
        "block_kind": "text",
        "source_type": "lmstudio",
        "system_template": _TEXT_FALLBACK_PROMPT["system"],
        "user_template": _TEXT_FALLBACK_PROMPT["user"],
        "parser_strategy": "plain_text",
        "notes": "Импорт из legacy build_strip_prompt (LM Studio вариант)",
    })

    return prompts


def get_prompt_template_id_for_block(
    block_kind: str,
    source_type: str,
    imported_prompts: dict[str, str],
) -> Optional[str]:
    """Найти prompt_template_id для блока по kind и source_type.

    imported_prompts: маппинг template_key → id (из результатов import-prompts)
    """
    key = f"legacy_{block_kind}_{source_type}"
    return imported_prompts.get(key)
