"""Импорт annotation.json → documents + document_pages + blocks.

Читает legacy annotations таблицу + tree_nodes, создаёт документы в новой БД.
Каждый документ — атомарная транзакция.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..config import MigrationConfig
from ..db import DatabaseClient
from ..mappers.block_mapper import extract_legacy_block_id, map_block
from ..mappers.document_mapper import (
    find_pdf_r2_key,
    map_document,
    map_document_pages,
    normalize_annotation_data,
)
from ..utils import MigrationState, MigrationSummary, console, create_progress

logger = logging.getLogger("migrate_legacy.annotation_importer")


def import_annotations(
    config: MigrationConfig,
    legacy_db: DatabaseClient,
    target_db: DatabaseClient,
    state: MigrationState,
    summary: MigrationSummary,
    node_id: Optional[str] = None,
    limit: int = 0,
) -> dict[str, dict[str, str]]:
    """Импортировать аннотации из legacy БД.

    Returns:
        Маппинг legacy_block_id → {"new_block_id": ..., "document_id": ...}
    """
    console.print("[bold]Импорт аннотаций...[/bold]")

    # Получить список аннотаций из legacy
    query = """
        SELECT a.id, a.node_id, a.data, a.format_version,
               tn.name, tn.code, tn.path
        FROM annotations a
        JOIN tree_nodes tn ON tn.id = a.node_id
        WHERE tn.node_type IN ('document', 'folder')
    """
    params: list = []

    if node_id:
        query += " AND a.node_id = %s"
        params.append(node_id)

    query += " ORDER BY tn.sort_order, tn.name"

    if limit > 0:
        query += " LIMIT %s"
        params.append(limit)

    annotations = legacy_db.execute(query, params if params else None)
    console.print(f"  Найдено аннотаций: {len(annotations)}")

    block_map: dict[str, dict[str, str]] = {}

    with create_progress() as progress:
        task = progress.add_task("Документы", total=len(annotations))

        for ann in annotations:
            legacy_node_id = str(ann["node_id"])

            # Skip existing?
            if config.skip_existing and state.has_document(legacy_node_id):
                summary.documents_skipped += 1
                progress.advance(task)
                continue

            try:
                _import_one_document(
                    config, legacy_db, target_db, ann, state, summary, block_map,
                )
            except Exception as e:
                summary.errors.append(f"Документ node_id={legacy_node_id}: {e}")
                logger.error("Ошибка миграции node_id=%s: %s", legacy_node_id, e)

            progress.advance(task)

    console.print(
        f"  Документов: создано={summary.documents_created}, пропущено={summary.documents_skipped}"
    )
    console.print(
        f"  Страниц: {summary.pages_created} | Блоков: {summary.blocks_created} "
        f"(table skip={summary.blocks_skipped_table})"
    )

    return block_map


def _import_one_document(
    config: MigrationConfig,
    legacy_db: DatabaseClient,
    target_db: DatabaseClient,
    annotation_row: dict,
    state: MigrationState,
    summary: MigrationSummary,
    block_map: dict[str, dict[str, str]],
) -> None:
    """Импортировать один документ (атомарная транзакция)."""
    legacy_node_id = str(annotation_row["node_id"])
    raw_data = annotation_row["data"]

    # Нормализация annotation data
    ann_data = normalize_annotation_data(raw_data)
    if not ann_data or not ann_data.get("pages"):
        summary.warnings.append(f"Пустая аннотация для node_id={legacy_node_id}")
        summary.documents_skipped += 1
        return

    # Найти R2 ключ PDF
    pdf_r2_key = find_pdf_r2_key(legacy_db, legacy_node_id)

    # Создать document dict
    doc_data = map_document(
        node=annotation_row,
        annotation_data=ann_data,
        workspace_id=config.workspace_id,
        document_profile_id=config.document_profile_id,
        pdf_r2_key=pdf_r2_key,
    )
    document_id = doc_data["id"]

    # Создать pages
    pages_data = map_document_pages(document_id, ann_data)

    # Создать blocks
    blocks_data: list[dict] = []
    reading_order = 1

    for page in ann_data.get("pages", []):
        page_width = page.get("width", 0)
        page_height = page.get("height", 0)

        for legacy_block in page.get("blocks", []):
            block_row = map_block(
                legacy_block,
                document_id,
                page_width=page_width,
                page_height=page_height,
                reading_order=reading_order,
            )

            if block_row is None:
                # table block — пропускаем
                summary.blocks_skipped_table += 1
                summary.warnings.append(
                    f"Пропущен table блок {extract_legacy_block_id(legacy_block)} "
                    f"в node_id={legacy_node_id}"
                )
                continue

            legacy_bid = extract_legacy_block_id(legacy_block)
            block_map[legacy_bid] = {
                "new_block_id": block_row["id"],
                "document_id": document_id,
            }
            blocks_data.append(block_row)
            reading_order += 1

    if config.dry_run:
        console.print(
            f"  [DRY-RUN] {annotation_row.get('name', '?')}: "
            f"{len(pages_data)} стр., {len(blocks_data)} блоков"
        )
        summary.documents_created += 1
        summary.pages_created += len(pages_data)
        summary.blocks_created += len(blocks_data)
        state.add_document(legacy_node_id, document_id)
        return

    # INSERT всё в одной транзакции
    with target_db.transaction() as cur:
        # Document
        cur.execute(
            """
            INSERT INTO documents
                (id, workspace_id, title, original_r2_key,
                 document_profile_id, status, page_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                doc_data["id"], doc_data["workspace_id"], doc_data["title"],
                doc_data["original_r2_key"], doc_data["document_profile_id"],
                doc_data["status"], doc_data["page_count"],
            ),
        )

        # Pages
        for p in pages_data:
            cur.execute(
                """
                INSERT INTO document_pages (id, document_id, page_number, width, height, rotation)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (p["id"], p["document_id"], p["page_number"], p["width"], p["height"], p["rotation"]),
            )

        # Blocks
        for b in blocks_data:
            cur.execute(
                """
                INSERT INTO blocks
                    (id, document_id, page_number, block_kind, shape_type,
                     bbox_json, polygon_json, reading_order, geometry_rev, content_rev,
                     manual_lock, current_status, current_text, crop_upload_state)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    b["id"], b["document_id"], b["page_number"], b["block_kind"],
                    b["shape_type"], json.dumps(b["bbox_json"]), json.dumps(b["polygon_json"]) if b["polygon_json"] else None,
                    b["reading_order"], b["geometry_rev"], b["content_rev"],
                    b["manual_lock"], b["current_status"], b["current_text"],
                    b["crop_upload_state"],
                ),
            )

    # Обновить state
    state.add_document(legacy_node_id, document_id)
    summary.documents_created += 1
    summary.pages_created += len(pages_data)
    summary.blocks_created += len(blocks_data)

    logger.info(
        "Документ %s: %d стр., %d блоков",
        annotation_row.get("name", "?"),
        len(pages_data),
        len(blocks_data),
    )
