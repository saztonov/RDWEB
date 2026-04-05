"""Индивидуальные проверки качества OCR результата.

Адаптация из legacy:
- text_ocr_quality.py (classify_text_output, filter_mixed_text_output)
- ocr_result.py (is_suspicious_output, is_error, is_non_retriable)
"""

from __future__ import annotations

import json
import re

# ── Паттерны suspicious output (из legacy is_suspicious_output) ──────

# JSON bbox dump вместо текста
_BBOX_JSON_RE = re.compile(r'"bbox"\s*:\s*\[[\d.,\s]+\]')
# Layout dump
_LAYOUT_DUMP_RE = re.compile(r'"(x|y|width|height|left|top|right|bottom)"\s*:\s*[\d.]+')
# Повторяющийся мусор
_REPETITIVE_RE = re.compile(r"(.{3,}?)\1{5,}")
# Чисто координатный вывод
_COORDS_ONLY_RE = re.compile(r"^[\d\s.,\[\]{}:\"xy]+$")

# ── Паттерны <think> тегов ─────────────────────────────────────────

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text: str) -> str:
    """Удалить <think>...</think> теги из ответа LLM."""
    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned if cleaned else text


def check_empty(text: str) -> bool:
    """Текст пустой или только whitespace."""
    return not text or not text.strip()


def check_too_short(text: str, min_length: int = 3) -> bool:
    """Текст слишком короткий для text-блока."""
    return len(text.strip()) < min_length


def check_suspicious_output(text: str) -> tuple[bool, str]:
    """Обнаружение layout/bbox dump вместо OCR результата.

    Returns:
        (is_suspicious, reason)
    """
    stripped = text.strip()

    # JSON bbox dumps
    bbox_matches = _BBOX_JSON_RE.findall(stripped)
    if len(bbox_matches) > 3:
        return True, "json_bbox_dump"

    # Layout coordinate dumps
    layout_matches = _LAYOUT_DUMP_RE.findall(stripped)
    if len(layout_matches) > 10:
        return True, "layout_dump"

    # Чисто координатный вывод
    if len(stripped) > 20 and _COORDS_ONLY_RE.match(stripped):
        return True, "coords_only"

    # Preformatted JSON table
    if stripped.startswith("[{") and stripped.endswith("}]"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list) and len(parsed) > 2:
                first_keys = set(parsed[0].keys()) if isinstance(parsed[0], dict) else set()
                if first_keys & {"x", "y", "bbox", "left", "top", "width", "height"}:
                    return True, "json_table_layout"
        except (json.JSONDecodeError, TypeError, IndexError):
            pass

    return False, ""


def check_garbage(text: str) -> bool:
    """Обнаружение мусорного вывода: non-printable и повторы."""
    stripped = text.strip()
    if not stripped:
        return False

    # Высокий процент non-printable
    non_printable = sum(1 for c in stripped if not c.isprintable() and c not in "\n\r\t")
    if len(stripped) > 10 and non_printable / len(stripped) > 0.3:
        return True

    # Повторяющийся паттерн
    if _REPETITIVE_RE.search(stripped):
        return True

    return False


def validate_stamp_json(text: str) -> tuple[bool, str]:
    """Валидация JSON для stamp блока.

    Returns:
        (is_valid, error_message)
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    if not isinstance(parsed, dict):
        return False, f"Expected object, got {type(parsed).__name__}"

    return True, ""


def validate_image_json(text: str) -> tuple[bool, str]:
    """Валидация JSON для image блока.

    Returns:
        (is_valid, error_message)
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"

    if not isinstance(parsed, dict):
        return False, f"Expected object, got {type(parsed).__name__}"

    return True, ""


def validate_html_fragment(text: str) -> tuple[bool, str]:
    """Базовая проверка HTML fragment.

    Returns:
        (is_valid, error_message)
    """
    stripped = text.strip()

    # Пустой — не валидный HTML fragment
    if not stripped:
        return False, "Empty HTML"

    # Хотя бы один HTML-тег должен быть
    if "<" not in stripped:
        # Может быть plain text — допустимо для text блоков
        return True, ""

    # Проверить баланс открывающих/закрывающих тегов (простая проверка)
    open_tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)[^>]*/?>", stripped)
    close_tags = re.findall(r"</([a-zA-Z][a-zA-Z0-9]*)>", stripped)

    # Грубая проверка — если вообще нет закрывающих при наличии открывающих
    void_tags = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col"}
    non_void_open = [t.lower() for t in open_tags if t.lower() not in void_tags]
    if len(non_void_open) > 3 and len(close_tags) == 0:
        return False, "No closing tags found"

    return True, ""
