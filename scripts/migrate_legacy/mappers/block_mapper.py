"""Маппинг legacy Block → new blocks row.

Ключевые преобразования:
- block_type=IMAGE + category_code="stamp" → block_kind='stamp'
- coords_px [x1,y1,x2,y2] → bbox_json {x, y, width, height}
- shape_type "rectangle" → "rect"
- page_index 0-based → page_number 1-based
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..utils import determine_block_status, is_ocr_success, new_uuid

logger = logging.getLogger("migrate_legacy.block_mapper")


def map_block_kind(block_type: str, category_code: Optional[str]) -> Optional[str]:
    """Преобразовать legacy block_type + category_code → new block_kind.

    Возвращает None для table (пропускаем с warning).
    """
    bt = block_type.lower().strip()

    if bt == "text":
        return "text"

    if bt == "image":
        if category_code and category_code.lower() == "stamp":
            return "stamp"
        return "image"

    if bt == "table":
        # Правило: table удалён из новой системы полностью
        return None

    logger.warning("Неизвестный block_type=%s, fallback → text", block_type)
    return "text"


def map_shape_type(legacy_shape: Optional[str]) -> str:
    """Преобразовать legacy shape_type → new shape_type enum."""
    if not legacy_shape:
        return "rect"
    s = legacy_shape.lower().strip()
    if s == "rectangle":
        return "rect"
    if s == "polygon":
        return "polygon"
    return "rect"


def map_bbox_json(coords_px: list, coords_norm: Optional[list] = None) -> dict:
    """Преобразовать legacy coords_px → new bbox_json.

    Legacy: [x1, y1, x2, y2] в пикселях
    New: {"x": x1, "y": y1, "width": x2-x1, "height": y2-y1}
    """
    x1, y1, x2, y2 = coords_px[:4]
    bbox = {
        "x": float(x1),
        "y": float(y1),
        "width": float(x2 - x1),
        "height": float(y2 - y1),
    }
    # Сохраняем normalized coords для верификации
    if coords_norm and len(coords_norm) >= 4:
        bbox["x_norm"] = float(coords_norm[0])
        bbox["y_norm"] = float(coords_norm[1])
        bbox["w_norm"] = float(coords_norm[2] - coords_norm[0])
        bbox["h_norm"] = float(coords_norm[3] - coords_norm[1])
    return bbox


def compute_coords_norm(
    coords_px: list, page_width: int, page_height: int,
) -> list[float]:
    """Вычислить coords_norm из coords_px и размеров страницы."""
    if page_width <= 0 or page_height <= 0:
        return [0.0, 0.0, 0.0, 0.0]
    x1, y1, x2, y2 = coords_px[:4]
    return [
        x1 / page_width,
        y1 / page_height,
        x2 / page_width,
        y2 / page_height,
    ]


def map_polygon_json(polygon_points: Optional[list]) -> Optional[list]:
    """Преобразовать legacy polygon_points → new polygon_json.

    Legacy: [[x1,y1], [x2,y2], ...] в пикселях
    New: [[x1,y1], [x2,y2], ...] (тот же формат)
    """
    if not polygon_points:
        return None
    return [[float(p[0]), float(p[1])] for p in polygon_points if len(p) >= 2]


def map_block(
    legacy_block: dict,
    document_id: str,
    page_width: int = 0,
    page_height: int = 0,
    reading_order: int = 1,
) -> Optional[dict]:
    """Преобразовать один legacy block dict → new blocks INSERT dict.

    Возвращает None если block_kind не поддерживается (table).
    """
    block_type = legacy_block.get("block_type", "text")
    category_code = legacy_block.get("category_code")

    block_kind = map_block_kind(block_type, category_code)
    if block_kind is None:
        return None

    # Координаты
    coords_px = legacy_block.get("coords_px", [0, 0, 0, 0])
    coords_norm = legacy_block.get("coords_norm")
    if not coords_norm and page_width > 0 and page_height > 0:
        coords_norm = compute_coords_norm(coords_px, page_width, page_height)

    # Статус
    ocr_text = legacy_block.get("ocr_text")
    is_correction = legacy_block.get("is_correction", False)
    current_status = determine_block_status(ocr_text, is_correction)

    # page_number: legacy 0-based → new 1-based
    page_index = legacy_block.get("page_index", 0)
    page_number = page_index + 1

    block_id = new_uuid()

    row: dict[str, Any] = {
        "id": block_id,
        "document_id": document_id,
        "page_number": page_number,
        "block_kind": block_kind,
        "shape_type": map_shape_type(legacy_block.get("shape_type")),
        "bbox_json": map_bbox_json(coords_px, coords_norm),
        "polygon_json": map_polygon_json(legacy_block.get("polygon_points")),
        "reading_order": reading_order,
        "geometry_rev": 1,
        "content_rev": 1,
        "manual_lock": False,
        "current_status": current_status,
        "current_text": ocr_text if is_ocr_success(ocr_text) else None,
        "crop_upload_state": "none",
    }

    # Для stamp блоков — проверить ocr_json для structured data
    if block_kind == "stamp":
        # Legacy хранит parsed stamp JSON в ocr_json (через result.json merger)
        # Это будет обогащено позже через import-result
        pass

    return row


def extract_legacy_block_id(legacy_block: dict) -> str:
    """Извлечь ID блока из legacy формата."""
    return legacy_block.get("id", "unknown")
