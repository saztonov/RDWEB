"""Crop блока из отрендеренной страницы PDF.

Адаптация из legacy StreamingPDFProcessor.crop_block_image().
Работает с нормализованными координатами [0..1] из bbox_json.
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def crop_block_image(
    page_image: Image.Image,
    bbox_json: dict[str, Any],
    polygon_json: list[list[float]] | None = None,
    shape_type: str = "rect",
    padding: int = 5,
) -> Image.Image:
    """Вырезать блок из page_image по нормализованным координатам.

    Args:
        page_image: Отрендеренная страница PDF (PIL Image).
        bbox_json: {"x": float, "y": float, "width": float, "height": float}
                   в нормализованных координатах [0..1].
        polygon_json: Список точек [[x, y], ...] для polygon shape.
        shape_type: "rect" или "polygon".
        padding: Отступ в пикселях вокруг bbox.

    Returns:
        PIL Image — вырезанный блок.
    """
    img_w, img_h = page_image.size

    # Конвертация нормализованных координат в пиксели
    x = bbox_json["x"] * img_w
    y = bbox_json["y"] * img_h
    w = bbox_json["width"] * img_w
    h = bbox_json["height"] * img_h

    # Bbox с padding, clamped к границам
    x1 = max(0, int(x - padding))
    y1 = max(0, int(y - padding))
    x2 = min(img_w, int(x + w + padding))
    y2 = min(img_h, int(y + h + padding))

    if x2 <= x1 or y2 <= y1:
        logger.warning(
            "Crop bbox пуст после clamp: bbox=%s, image=%dx%d",
            bbox_json, img_w, img_h,
        )
        # Возвращаем минимальный 1x1 белый пиксель
        return Image.new("RGB", (1, 1), (255, 255, 255))

    crop = page_image.crop((x1, y1, x2, y2))

    # Для polygon: применить маску
    if shape_type == "polygon" and polygon_json:
        crop = _apply_polygon_mask(crop, polygon_json, x1, y1, img_w, img_h)

    return crop


def _apply_polygon_mask(
    crop: Image.Image,
    polygon_json: list[list[float]],
    crop_x: int,
    crop_y: int,
    img_w: int,
    img_h: int,
) -> Image.Image:
    """Применить polygon-маску к crop-у.

    Точки polygon в нормализованных координатах пересчитываются
    в координаты crop-а. Пиксели за пределами polygon заливаются белым.
    """
    crop_w, crop_h = crop.size

    # Перевод polygon точек в координаты crop-а
    crop_points: list[tuple[int, int]] = []
    for point in polygon_json:
        px = int(point[0] * img_w) - crop_x
        py = int(point[1] * img_h) - crop_y
        crop_points.append((px, py))

    if len(crop_points) < 3:
        return crop

    # Создаём маску: белый внутри polygon, чёрный снаружи
    mask = Image.new("L", (crop_w, crop_h), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(crop_points, fill=255)

    # Белый фон + наложение crop через маску
    result = Image.new("RGB", (crop_w, crop_h), (255, 255, 255))
    result.paste(crop, (0, 0), mask)

    return result
