"""Dirty detection — определение блоков, требующих (пере)распознавания.

Используется при smart rerun для фильтрации блоков.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .signature import compute_recognition_signature, is_block_dirty


@dataclass
class DirtyResult:
    """Результат анализа dirty-блоков документа."""
    total: int = 0
    dirty_count: int = 0
    locked_count: int = 0
    dirty_block_ids: list[str] = field(default_factory=list)


def _get_prompt_template_version(prompt_template_id: str | None, sb) -> int | None:
    """Получить текущую version prompt template из БД."""
    if not prompt_template_id:
        return None
    result = (
        sb.table("prompt_templates")
        .select("version")
        .eq("id", prompt_template_id)
        .maybe_single()
        .execute()
    )
    if result.data:
        return result.data["version"]
    return None


def get_dirty_blocks(document_id: str, sb) -> DirtyResult:
    """Определить dirty-блоки документа для smart rerun.

    Блок считается dirty если:
    1. current_status = 'pending' (новый блок)
    2. last_recognition_signature IS NULL (route/model/prompt изменены)
    3. Вычисленная signature ≠ last_recognition_signature (geometry/kind changed)
    4. current_status IN ('failed', 'manual_review') и manual_lock = false

    Блоки с manual_lock = true пропускаются.
    """
    # Загрузить все активные блоки документа
    result = (
        sb.table("blocks")
        .select("id, block_kind, geometry_rev, manual_lock, current_status, "
                "route_source_id, route_model_name, prompt_template_id, "
                "last_recognition_signature")
        .eq("document_id", document_id)
        .is_("deleted_at", "null")
        .execute()
    )

    blocks = result.data or []
    dirty = DirtyResult(total=len(blocks))

    # Кэш версий prompt templates (чтобы не дёргать БД на каждый блок)
    pt_version_cache: dict[str, int | None] = {}

    for block in blocks:
        if block["manual_lock"]:
            dirty.locked_count += 1
            continue

        block_dirty = False

        # 1. Новый блок
        if block["current_status"] == "pending":
            block_dirty = True

        # 4. Ранее провалившийся / на ручной проверке
        elif block["current_status"] in ("failed", "manual_review"):
            block_dirty = True

        # 2+3. Signature changed
        else:
            pt_id = block.get("prompt_template_id")
            if pt_id not in pt_version_cache:
                pt_version_cache[pt_id] = _get_prompt_template_version(pt_id, sb)

            current_sig = compute_recognition_signature(
                geometry_rev=block["geometry_rev"],
                block_kind=block["block_kind"],
                route_source_id=block.get("route_source_id"),
                route_model_name=block.get("route_model_name"),
                prompt_template_id=pt_id,
                prompt_template_version=pt_version_cache[pt_id],
            )

            if is_block_dirty(block, current_sig):
                block_dirty = True

        if block_dirty:
            dirty.dirty_count += 1
            dirty.dirty_block_ids.append(block["id"])

    return dirty
