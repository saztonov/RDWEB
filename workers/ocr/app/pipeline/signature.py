"""Расширенная сигнатура для OCR pipeline — включает crop_sha256 и parser_version.

Дополняет services/api/app/services/signature.py, которая используется для
dirty detection без crop_sha256 (crop ещё не создан на этапе API).

Worker строит полную сигнатуру с crop_sha256 после рендеринга crop.
"""

from __future__ import annotations

import hashlib


def build_pipeline_signature(
    geometry_rev: int,
    block_kind: str,
    source_id: str,
    model_name: str,
    prompt_template_id: str,
    prompt_template_version: int,
    parser_version: str,
    crop_sha256: str,
) -> str:
    """SHA-256 от канонической строки всех параметров OCR.

    Включает crop_sha256 — гарантирует что при изменении PDF
    (или его рендеринга) блок будет перераспознан.
    """
    canonical = "|".join([
        str(geometry_rev),
        block_kind,
        source_id or "",
        model_name or "",
        prompt_template_id or "",
        str(prompt_template_version) if prompt_template_version is not None else "",
        parser_version or "1",
        crop_sha256 or "",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_signature_match(block_data: dict, new_signature: str) -> bool:
    """True если блок уже распознан с точно такой же сигнатурой."""
    stored = block_data.get("last_recognition_signature")
    if stored is None:
        return False
    if stored != new_signature:
        return False
    return block_data.get("current_status") == "recognized"


def compute_crop_sha256(png_bytes: bytes) -> str:
    """SHA-256 от PNG bytes crop-а."""
    return hashlib.sha256(png_bytes).hexdigest()
