"""Сервис подписи распознавания — dirty detection для smart rerun.

Signature кодирует все параметры, влияющие на результат OCR:
geometry_rev, block_kind, route, model, prompt template + version.
Изменение любого из них делает блок «грязным».
"""

from __future__ import annotations

import hashlib


def compute_recognition_signature(
    geometry_rev: int,
    block_kind: str,
    route_source_id: str | None,
    route_model_name: str | None,
    prompt_template_id: str | None,
    prompt_template_version: int | None,
) -> str:
    """Вычислить SHA-256 от канонической строки параметров распознавания.

    Детерминированная функция: одинаковые входные → одинаковый hash.
    """
    canonical = "|".join([
        str(geometry_rev),
        block_kind,
        route_source_id or "",
        route_model_name or "",
        prompt_template_id or "",
        str(prompt_template_version) if prompt_template_version is not None else "",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_block_dirty(
    block: dict,
    current_signature: str,
) -> bool:
    """Проверить, отличается ли текущая signature от сохранённой.

    Блок dirty если:
    - last_recognition_signature is None (никогда не распознавался или route изменён)
    - last_recognition_signature != current_signature
    """
    stored = block.get("last_recognition_signature")
    if stored is None:
        return True
    return stored != current_signature
