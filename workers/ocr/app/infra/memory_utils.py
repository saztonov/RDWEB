"""Утилиты мониторинга памяти — адаптация из legacy memory_utils.py.

Baseline + delta паттерн для отслеживания потребления по фазам.
"""

from __future__ import annotations

import gc
import logging

from PIL import Image

logger = logging.getLogger(__name__)


def get_memory_mb() -> float:
    """Текущее RSS потребление процесса в MB."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


def log_memory(label: str) -> float:
    """Залогировать текущее потребление памяти. Возвращает RSS в MB."""
    mb = get_memory_mb()
    logger.info("Memory [%s]: %.1f MB RSS", label, mb)
    return mb


def log_memory_delta(label: str, start_mb: float) -> float:
    """Залогировать изменение памяти относительно baseline."""
    current = get_memory_mb()
    delta = current - start_mb
    sign = "+" if delta >= 0 else ""
    logger.info("Memory [%s]: %.1f MB RSS (%s%.1f MB)", label, current, sign, delta)
    return current


def force_gc(label: str = "") -> None:
    """Принудительный GC с логированием результата."""
    before = get_memory_mb()
    gc.collect()
    after = get_memory_mb()
    freed = before - after
    if freed > 1.0:
        logger.info("GC [%s]: freed %.1f MB (%.1f → %.1f)", label, freed, before, after)


def get_pil_image_size_mb(img: Image.Image) -> float:
    """Расчёт размера PIL Image в MB (width * height * channels / 1024^2)."""
    w, h = img.size
    channels = len(img.getbands())
    return (w * h * channels) / (1024 * 1024)
