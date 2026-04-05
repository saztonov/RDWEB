"""OCR Core — ядро OCR системы."""

from .models import BlockKind, ShapeType
from .pdf_cache import PdfCacheManager

__all__ = ["BlockKind", "PdfCacheManager", "ShapeType"]
