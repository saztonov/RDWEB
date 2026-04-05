"""Recognition service — бизнес-логика smart recognition и manual edits.

Ключевые функции:
- apply_manual_edit: ручная правка текста с автоблокировкой
- toggle_lock: переключение manual_lock
- accept_attempt: принятие candidate attempt как current
- apply_recognition_result: применение результата OCR (вызывается worker-ом)
- start_recognition_run: создание и запуск recognition run
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from ..logging_config import get_logger
from .dirty_detection import get_dirty_blocks
from .signature import compute_recognition_signature

_logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _get_block(block_id: str, sb, *, include_deleted: bool = False) -> dict:
    """Загрузить блок из БД. Raises ValueError если не найден."""
    query = sb.table("blocks").select("*").eq("id", block_id)
    if not include_deleted:
        query = query.is_("deleted_at", "null")
    result = query.single().execute()
    if not result.data:
        raise ValueError(f"Блок {block_id} не найден")
    return result.data


def _create_block_version(
    block_id: str,
    version_number: int,
    change_type: str,
    snapshot: dict,
    user_id: str,
    sb,
) -> None:
    """Создать запись в block_versions."""
    sb.table("block_versions").insert({
        "block_id": block_id,
        "version_number": version_number,
        "change_type": change_type,
        "snapshot_json": snapshot,
        "created_by": user_id,
    }).execute()


def _create_block_event(
    block_id: str,
    event_type: str,
    payload: dict,
    actor_id: str,
    sb,
) -> None:
    """Создать запись в block_events."""
    sb.table("block_events").insert({
        "block_id": block_id,
        "event_type": event_type,
        "payload_json": payload,
        "actor_id": actor_id,
    }).execute()


def _block_snapshot(block: dict) -> dict:
    """Сделать снимок блока для block_versions."""
    return {
        "current_text": block.get("current_text"),
        "current_structured_json": block.get("current_structured_json"),
        "current_render_html": block.get("current_render_html"),
        "current_status": block.get("current_status"),
        "current_attempt_id": block.get("current_attempt_id"),
        "geometry_rev": block.get("geometry_rev"),
        "content_rev": block.get("content_rev"),
        "manual_lock": block.get("manual_lock"),
        "last_recognition_signature": block.get("last_recognition_signature"),
    }


def _get_next_version_number(block_id: str, sb) -> int:
    """Получить следующий номер версии блока."""
    result = (
        sb.table("block_versions")
        .select("version_number")
        .eq("block_id", block_id)
        .order("version_number", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["version_number"] + 1
    return 1


# ──────────────────────────────────────────────────────────────────────
# Manual Edit
# ──────────────────────────────────────────────────────────────────────

def apply_manual_edit(
    block_id: str,
    user_id: str,
    current_text: str | None,
    current_structured_json: dict | None,
    sb,
) -> dict:
    """Применить ручную правку текста блока.

    Правила:
    1. content_rev += 1
    2. manual_lock = true
    3. current_status = 'recognized'
    4. Создать block_version + block_event
    """
    block = _get_block(block_id, sb)

    update_data: dict[str, Any] = {
        "content_rev": block["content_rev"] + 1,
        "manual_lock": True,
        "current_status": "recognized",
        "updated_by": user_id,
    }

    if current_text is not None:
        update_data["current_text"] = current_text
    if current_structured_json is not None:
        update_data["current_structured_json"] = current_structured_json

    result = sb.table("blocks").update(update_data).eq("id", block_id).execute()
    if not result.data:
        raise ValueError(f"Не удалось обновить блок {block_id}")

    updated_block = result.data[0]

    # Снимок для версионирования
    version_num = _get_next_version_number(block_id, sb)
    _create_block_version(
        block_id, version_num, "manual_edit",
        _block_snapshot(updated_block), user_id, sb,
    )
    _create_block_event(
        block_id, "manual_edit",
        {"content_rev": updated_block["content_rev"]},
        user_id, sb,
    )

    _logger.info(
        "Manual edit applied",
        extra={
            "event": "manual_edit",
            "block_id": block_id,
            "content_rev": updated_block["content_rev"],
            "user_id": user_id,
        },
    )

    return updated_block


# ──────────────────────────────────────────────────────────────────────
# Lock Toggle
# ──────────────────────────────────────────────────────────────────────

def toggle_lock(
    block_id: str,
    manual_lock: bool,
    user_id: str,
    sb,
) -> dict:
    """Переключить manual_lock на блоке."""
    block = _get_block(block_id, sb)

    if block["manual_lock"] == manual_lock:
        return block  # Уже в нужном состоянии

    result = (
        sb.table("blocks")
        .update({"manual_lock": manual_lock, "updated_by": user_id})
        .eq("id", block_id)
        .execute()
    )
    if not result.data:
        raise ValueError(f"Не удалось обновить блок {block_id}")

    event_type = "locked" if manual_lock else "unlocked"
    _create_block_event(block_id, event_type, {}, user_id, sb)

    _logger.info(
        f"Block {event_type}",
        extra={"event": f"block_{event_type}", "block_id": block_id, "user_id": user_id},
    )

    return result.data[0]


# ──────────────────────────────────────────────────────────────────────
# Accept Attempt
# ──────────────────────────────────────────────────────────────────────

def accept_attempt(
    block_id: str,
    attempt_id: str,
    user_id: str,
    sb,
) -> dict:
    """Принять candidate attempt как текущий результат блока.

    1. Загружает attempt
    2. Копирует normalized_text → current_text и т.д.
    3. Обновляет selected_as_current на обоих attempt-ах
    4. Создаёт block_version + block_event
    """
    block = _get_block(block_id, sb)

    # Загрузить attempt
    attempt_result = (
        sb.table("recognition_attempts")
        .select("*")
        .eq("id", attempt_id)
        .eq("block_id", block_id)
        .single()
        .execute()
    )
    if not attempt_result.data:
        raise ValueError(f"Attempt {attempt_id} не найден для блока {block_id}")

    attempt = attempt_result.data

    if attempt["status"] != "success":
        raise ValueError(f"Невозможно принять attempt со статусом '{attempt['status']}'")

    # Снять selected_as_current с предыдущего attempt
    old_attempt_id = block.get("current_attempt_id")
    if old_attempt_id:
        sb.table("recognition_attempts").update(
            {"selected_as_current": False}
        ).eq("id", old_attempt_id).execute()

    # Установить selected_as_current на новом
    sb.table("recognition_attempts").update(
        {"selected_as_current": True}
    ).eq("id", attempt_id).execute()

    # Обновить блок
    update_data: dict[str, Any] = {
        "current_text": attempt.get("normalized_text"),
        "current_structured_json": attempt.get("structured_json"),
        "current_render_html": attempt.get("render_html"),
        "current_attempt_id": attempt_id,
        "current_status": "recognized",
        "content_rev": block["content_rev"] + 1,
        "updated_by": user_id,
    }

    result = sb.table("blocks").update(update_data).eq("id", block_id).execute()
    if not result.data:
        raise ValueError(f"Не удалось обновить блок {block_id}")

    updated_block = result.data[0]

    # Версия + событие
    version_num = _get_next_version_number(block_id, sb)
    _create_block_version(
        block_id, version_num, "content",
        _block_snapshot(updated_block), user_id, sb,
    )
    _create_block_event(
        block_id, "attempt_accepted",
        {"attempt_id": attempt_id, "content_rev": updated_block["content_rev"]},
        user_id, sb,
    )

    _logger.info(
        "Attempt accepted",
        extra={
            "event": "attempt_accepted",
            "block_id": block_id,
            "attempt_id": attempt_id,
            "user_id": user_id,
        },
    )

    return updated_block


# ──────────────────────────────────────────────────────────────────────
# Apply Recognition Result (вызывается worker-ом)
# ──────────────────────────────────────────────────────────────────────

def apply_recognition_result(
    block_id: str,
    attempt_id: str,
    sb,
) -> dict:
    """Применить результат OCR-распознавания.

    Если manual_lock = true → attempt сохранён, но НЕ применён к block.current_*.
    Если manual_lock = false → копирует результат + вычисляет signature.
    """
    block = _get_block(block_id, sb)

    attempt_result = (
        sb.table("recognition_attempts")
        .select("*")
        .eq("id", attempt_id)
        .single()
        .execute()
    )
    if not attempt_result.data:
        raise ValueError(f"Attempt {attempt_id} не найден")

    attempt = attempt_result.data

    if block["manual_lock"]:
        # Не применяем — оставляем attempt как candidate
        _logger.info(
            "Block is locked, attempt stored as candidate",
            extra={
                "event": "recognition_candidate",
                "block_id": block_id,
                "attempt_id": attempt_id,
            },
        )
        return block

    # Снять selected_as_current с предыдущего attempt
    old_attempt_id = block.get("current_attempt_id")
    if old_attempt_id:
        sb.table("recognition_attempts").update(
            {"selected_as_current": False}
        ).eq("id", old_attempt_id).execute()

    # Установить selected_as_current на новом
    sb.table("recognition_attempts").update(
        {"selected_as_current": True}
    ).eq("id", attempt_id).execute()

    # Вычислить signature
    pt_version = None
    pt_id = block.get("prompt_template_id")
    if pt_id:
        pt_result = (
            sb.table("prompt_templates")
            .select("version")
            .eq("id", pt_id)
            .maybe_single()
            .execute()
        )
        if pt_result.data:
            pt_version = pt_result.data["version"]

    signature = compute_recognition_signature(
        geometry_rev=block["geometry_rev"],
        block_kind=block["block_kind"],
        route_source_id=block.get("route_source_id"),
        route_model_name=block.get("route_model_name"),
        prompt_template_id=pt_id,
        prompt_template_version=pt_version,
    )

    # Определить статус на основе результата attempt
    new_status = "recognized"
    if attempt["status"] == "failed":
        new_status = "failed"

    update_data: dict[str, Any] = {
        "current_text": attempt.get("normalized_text"),
        "current_structured_json": attempt.get("structured_json"),
        "current_render_html": attempt.get("render_html"),
        "current_attempt_id": attempt_id,
        "current_status": new_status,
        "content_rev": block["content_rev"] + 1,
        "last_recognition_signature": signature,
    }

    result = sb.table("blocks").update(update_data).eq("id", block_id).execute()
    if not result.data:
        raise ValueError(f"Не удалось обновить блок {block_id}")

    _logger.info(
        "Recognition result applied",
        extra={
            "event": "recognition_applied",
            "block_id": block_id,
            "attempt_id": attempt_id,
            "status": new_status,
        },
    )

    return result.data[0]


# ──────────────────────────────────────────────────────────────────────
# Recognition Run Management
# ──────────────────────────────────────────────────────────────────────

def start_recognition_run(
    document_id: str,
    run_mode: str,
    user_id: str,
    sb,
    block_ids: list[str] | None = None,
) -> dict:
    """Создать recognition_run и определить блоки для обработки.

    run_mode: 'smart' | 'full' | 'block_rerun'
    block_ids: для block_rerun — список конкретных block ID
    """
    if run_mode == "block_rerun" and not block_ids:
        raise ValueError("block_ids обязателен для режима block_rerun")

    if run_mode == "smart":
        dirty = get_dirty_blocks(document_id, sb)
        target_block_ids = dirty.dirty_block_ids
        dirty_count = dirty.dirty_count
    elif run_mode == "full":
        # Все блоки кроме locked
        blocks_result = (
            sb.table("blocks")
            .select("id, manual_lock")
            .eq("document_id", document_id)
            .is_("deleted_at", "null")
            .execute()
        )
        all_blocks = blocks_result.data or []
        target_block_ids = [b["id"] for b in all_blocks if not b["manual_lock"]]
        dirty_count = len(target_block_ids)
    elif run_mode == "block_rerun":
        target_block_ids = block_ids  # type: ignore[assignment]
        dirty_count = len(target_block_ids)
    else:
        raise ValueError(f"Неизвестный run_mode: {run_mode}")

    # Создать run
    run_data = {
        "document_id": document_id,
        "initiated_by": user_id,
        "run_mode": run_mode,
        "status": "pending",
        "total_blocks": dirty_count,
        "dirty_blocks": dirty_count,
        "processed_blocks": 0,
        "recognized_blocks": 0,
        "failed_blocks": 0,
        "manual_review_blocks": 0,
    }

    run_result = sb.table("recognition_runs").insert(run_data).execute()
    if not run_result.data:
        raise ValueError("Не удалось создать recognition_run")

    run = run_result.data[0]

    # Обновить статус блоков на 'queued'
    if target_block_ids:
        for bid in target_block_ids:
            sb.table("blocks").update({
                "current_status": "queued",
            }).eq("id", bid).is_("deleted_at", "null").execute()

    # Группировка блоков по page_number и dispatch page tasks
    if target_block_ids:
        page_blocks = _group_by_page(target_block_ids, sb)
        _dispatch_page_tasks(run["id"], document_id, page_blocks)

    _logger.info(
        "Recognition run created",
        extra={
            "event": "recognition_run_created",
            "run_id": run["id"],
            "document_id": document_id,
            "run_mode": run_mode,
            "target_blocks": len(target_block_ids),
            "page_groups": len(page_blocks) if target_block_ids else 0,
            "user_id": user_id,
        },
    )

    return {
        "run": run,
        "target_block_ids": target_block_ids,
    }


def _group_by_page(block_ids: list[str], sb) -> dict[int, list[str]]:
    """Сгруппировать block_ids по page_number."""
    if not block_ids:
        return {}

    result = (
        sb.table("blocks")
        .select("id, page_number")
        .in_("id", block_ids)
        .execute()
    )
    page_blocks: dict[int, list[str]] = {}
    for row in result.data or []:
        page = row["page_number"]
        page_blocks.setdefault(page, []).append(row["id"])
    return page_blocks


def _dispatch_page_tasks(
    run_id: str,
    document_id: str,
    page_blocks: dict[int, list[str]],
) -> None:
    """Отправить Celery task для каждой страницы."""
    from ..celery_client import get_celery_app
    app = get_celery_app()

    for page_number, block_ids in sorted(page_blocks.items()):
        app.send_task(
            "ocr.process_page_blocks",
            args=[run_id, document_id, page_number, block_ids],
            priority=5,
        )
        _logger.info(
            "Page task dispatched",
            extra={
                "event": "page_task_dispatched",
                "run_id": run_id,
                "page_number": page_number,
                "blocks": len(block_ids),
            },
        )


def get_block_attempts(block_id: str, sb) -> list[dict]:
    """Получить все recognition_attempts блока, отсортированные по дате."""
    result = (
        sb.table("recognition_attempts")
        .select("*")
        .eq("block_id", block_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def get_block_detail(block_id: str, sb) -> dict:
    """Получить полную информацию о блоке включая provenance текущего attempt."""
    block = _get_block(block_id, sb)

    # Если есть текущий attempt — загрузить его детали
    attempt_detail = None
    attempt_id = block.get("current_attempt_id")
    if attempt_id:
        attempt_result = (
            sb.table("recognition_attempts")
            .select("id, source_id, model_name, prompt_template_id, "
                    "attempt_no, fallback_no, status, started_at, finished_at")
            .eq("id", attempt_id)
            .maybe_single()
            .execute()
        )
        if attempt_result.data:
            attempt_detail = attempt_result.data

            # Получить имя source
            if attempt_detail.get("source_id"):
                source_result = (
                    sb.table("ocr_sources")
                    .select("name")
                    .eq("id", attempt_detail["source_id"])
                    .maybe_single()
                    .execute()
                )
                if source_result.data:
                    attempt_detail["source_name"] = source_result.data["name"]

            # Получить key + version prompt template
            if attempt_detail.get("prompt_template_id"):
                pt_result = (
                    sb.table("prompt_templates")
                    .select("template_key, version")
                    .eq("id", attempt_detail["prompt_template_id"])
                    .maybe_single()
                    .execute()
                )
                if pt_result.data:
                    attempt_detail["prompt_key"] = pt_result.data["template_key"]
                    attempt_detail["prompt_version"] = pt_result.data["version"]

    # Подсчитать количество attempts
    attempts_count_result = (
        sb.table("recognition_attempts")
        .select("id", count="exact")
        .eq("block_id", block_id)
        .execute()
    )
    attempts_count = attempts_count_result.count or 0

    # Проверить есть ли pending candidate (successful attempt, не selected_as_current)
    candidate_result = (
        sb.table("recognition_attempts")
        .select("id, normalized_text, model_name, created_at")
        .eq("block_id", block_id)
        .eq("status", "success")
        .eq("selected_as_current", False)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    pending_candidate = candidate_result.data[0] if candidate_result.data else None

    return {
        "block": block,
        "current_attempt": attempt_detail,
        "attempts_count": attempts_count,
        "pending_candidate": pending_candidate,
    }
