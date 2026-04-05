"""Импорт result.json → recognition_attempts + обогащение blocks.

Читает legacy result.json (из R2 или локального файла), создаёт
синтетические recognition_runs и recognition_attempts в новой БД.
Обогащает blocks данными из result.json (render_html, structured_json, crop_key).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import MigrationConfig
from ..db import DatabaseClient
from ..mappers.result_mapper import (
    build_block_index,
    map_block_enrichment,
    map_recognition_attempt,
    parse_result_json,
)
from ..utils import MigrationState, MigrationSummary, console, create_progress, new_uuid, now_utc

logger = logging.getLogger("migrate_legacy.result_importer")


def import_results(
    config: MigrationConfig,
    legacy_db: DatabaseClient,
    target_db: DatabaseClient,
    state: MigrationState,
    summary: MigrationSummary,
    block_map: dict[str, dict[str, str]],
    prompt_map: dict[str, str],
    node_id: Optional[str] = None,
) -> None:
    """Импортировать OCR результаты из legacy result.json.

    Для каждого документа:
    1. Найти result.json в legacy (job_files или node_files)
    2. Создать recognition_run
    3. Для каждого блока с OCR текстом → recognition_attempt
    4. Обогатить blocks данными из result.json
    """
    console.print("[bold]Импорт OCR результатов...[/bold]")

    # Получить документы из legacy
    query = """
        SELECT a.node_id, a.data, tn.name
        FROM annotations a
        JOIN tree_nodes tn ON tn.id = a.node_id
        WHERE tn.node_type IN ('document', 'folder')
    """
    params: list = []
    if node_id:
        query += " AND a.node_id = %s"
        params.append(node_id)

    annotations = legacy_db.execute(query, params if params else None)

    with create_progress() as progress:
        task = progress.add_task("Результаты", total=len(annotations))

        for ann in annotations:
            legacy_node_id = str(ann["node_id"])

            # Документ должен быть уже импортирован
            doc_id = state.get_document_id(legacy_node_id)
            if not doc_id:
                progress.advance(task)
                continue

            # Уже обработан?
            if config.skip_existing and state.has_run(legacy_node_id):
                progress.advance(task)
                continue

            try:
                _import_results_for_document(
                    config, legacy_db, target_db, ann, doc_id,
                    state, summary, block_map, prompt_map,
                )
            except Exception as e:
                summary.errors.append(f"Результаты node_id={legacy_node_id}: {e}")
                logger.error("Ошибка импорта результатов node_id=%s: %s", legacy_node_id, e)

            progress.advance(task)

    console.print(f"  Recognition runs: {summary.runs_created}")
    console.print(f"  Recognition attempts: {summary.attempts_created}")


def _import_results_for_document(
    config: MigrationConfig,
    legacy_db: DatabaseClient,
    target_db: DatabaseClient,
    annotation_row: dict,
    document_id: str,
    state: MigrationState,
    summary: MigrationSummary,
    block_map: dict[str, dict[str, str]],
    prompt_map: dict[str, str],
) -> None:
    """Импортировать результаты для одного документа."""
    legacy_node_id = str(annotation_row["node_id"])
    ann_data = annotation_row["data"]

    if isinstance(ann_data, str):
        ann_data = json.loads(ann_data)

    # Загрузить result.json из legacy (если есть)
    result_data = _load_result_json(legacy_db, legacy_node_id)
    result_index = build_block_index(result_data) if result_data else {}

    # Определить default source_id
    default_source_id = _resolve_default_source(config, legacy_db, legacy_node_id)
    if not default_source_id:
        summary.warnings.append(f"Нет OCR source для node_id={legacy_node_id}")
        return

    # Собрать все блоки с OCR текстом
    blocks_with_ocr = []
    for page in ann_data.get("pages", []):
        for legacy_block in page.get("blocks", []):
            legacy_bid = legacy_block.get("id", "")
            mapping = block_map.get(legacy_bid)
            if not mapping:
                continue

            ocr_text = legacy_block.get("ocr_text")
            if ocr_text is None or not ocr_text.strip():
                continue

            blocks_with_ocr.append((legacy_block, mapping, result_index.get(legacy_bid)))

    if not blocks_with_ocr:
        return

    # Определить prompt_template_id
    # Используем первый legacy промпт для соответствующего source_type
    default_prompt_id = prompt_map.get("legacy_text_openrouter")

    run_id = new_uuid()

    if config.dry_run:
        console.print(
            f"  [DRY-RUN] {annotation_row.get('name', '?')}: "
            f"1 run, {len(blocks_with_ocr)} attempts"
        )
        summary.runs_created += 1
        summary.attempts_created += len(blocks_with_ocr)
        state.add_run(legacy_node_id, run_id)
        return

    with target_db.transaction() as cur:
        # Создать recognition_run
        cur.execute(
            """
            INSERT INTO recognition_runs
                (id, document_id, initiated_by, run_mode, status,
                 total_blocks, processed_blocks, recognized_blocks, failed_blocks,
                 started_at, finished_at)
            VALUES (%s, %s, %s, 'full', 'completed', %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id, document_id,
                config.migrator_user_id or "00000000-0000-0000-0000-000000000000",
                len(blocks_with_ocr), len(blocks_with_ocr),
                sum(1 for b, _, _ in blocks_with_ocr if not _is_error(b)),
                sum(1 for b, _, _ in blocks_with_ocr if _is_error(b)),
                now_utc(), now_utc(),
            ),
        )

        # Создать attempts и обогатить blocks
        for legacy_block, mapping, result_block in blocks_with_ocr:
            block_kind = legacy_block.get("block_type", "text").lower()
            cat_code = legacy_block.get("category_code")
            if block_kind == "image" and cat_code == "stamp":
                kind_for_prompt = "stamp"
            elif block_kind == "image":
                kind_for_prompt = "image"
            else:
                kind_for_prompt = "text"

            prompt_id = prompt_map.get(f"legacy_{kind_for_prompt}_openrouter", default_prompt_id)

            attempt = map_recognition_attempt(
                block_id=mapping["new_block_id"],
                run_id=run_id,
                legacy_block=legacy_block,
                result_block=result_block,
                source_id=default_source_id,
                prompt_template_id=prompt_id,
            )

            if attempt:
                cur.execute(
                    """
                    INSERT INTO recognition_attempts
                        (id, run_id, block_id, geometry_rev, source_id, model_name,
                         prompt_template_id, prompt_snapshot_json, attempt_no, fallback_no,
                         status, normalized_text, render_html, structured_json,
                         quality_flags_json, error_message, selected_as_current,
                         started_at, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        attempt["id"], attempt["run_id"], attempt["block_id"],
                        attempt["geometry_rev"], attempt["source_id"], attempt["model_name"],
                        attempt["prompt_template_id"], attempt["prompt_snapshot_json"],
                        attempt["attempt_no"], attempt["fallback_no"],
                        attempt["status"], attempt.get("normalized_text"),
                        attempt.get("render_html"), attempt.get("structured_json"),
                        attempt.get("quality_flags_json"), attempt.get("error_message"),
                        attempt.get("selected_as_current", False),
                        now_utc(), now_utc(),
                    ),
                )

                # Обновить current_attempt_id в blocks
                if attempt.get("selected_as_current"):
                    cur.execute(
                        "UPDATE blocks SET current_attempt_id = %s WHERE id = %s",
                        (attempt["id"], mapping["new_block_id"]),
                    )

                summary.attempts_created += 1

            # Обогатить block из result.json
            enrichment = map_block_enrichment(result_block)
            if enrichment:
                set_clauses = ", ".join(f"{k} = %s" for k in enrichment)
                cur.execute(
                    f"UPDATE blocks SET {set_clauses} WHERE id = %s",
                    (*enrichment.values(), mapping["new_block_id"]),
                )

    state.add_run(legacy_node_id, run_id)
    summary.runs_created += 1


def _load_result_json(legacy_db: DatabaseClient, node_id: str) -> Optional[dict]:
    """Загрузить result.json из legacy БД (node_files или job_files)."""
    # Пробуем node_files
    row = legacy_db.execute_one(
        """
        SELECT metadata FROM node_files
        WHERE node_id = %s AND file_type = 'result_json'
        ORDER BY created_at DESC LIMIT 1
        """,
        (node_id,),
    )
    if row and row.get("metadata"):
        return parse_result_json(row["metadata"])

    # Fallback: данные из annotation.data (legacy хранит OCR результаты inline)
    return None


def _resolve_default_source(
    config: MigrationConfig,
    legacy_db: DatabaseClient,
    node_id: str,
) -> Optional[str]:
    """Определить default ocr_source_id для документа."""
    # Сначала из маппинга engine → source
    if config.engine_source_map:
        # Пробуем определить engine из последнего job
        row = legacy_db.execute_one(
            """
            SELECT engine FROM jobs
            WHERE node_id = %s AND status = 'done'
            ORDER BY completed_at DESC NULLS LAST LIMIT 1
            """,
            (node_id,),
        )
        if row and row.get("engine"):
            engine = row["engine"]
            source_id = config.engine_source_map.get(engine)
            if source_id:
                return source_id

    # Fallback: первый source из маппинга
    if config.engine_source_map:
        return next(iter(config.engine_source_map.values()))

    return None


def _is_error(legacy_block: dict) -> bool:
    """Проверить что legacy блок содержит ошибку OCR."""
    from ..utils import is_ocr_error
    return is_ocr_error(legacy_block.get("ocr_text"))
