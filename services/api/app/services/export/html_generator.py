"""Генератор HTML документа из текущего состояния блоков в БД.

Адаптация legacy rd_core/ocr/html_generator.py.
Source of truth — PostgreSQL (current_render_html, current_structured_json, current_text).
"""
import json as json_module
import logging
import re
from itertools import groupby
from typing import Any, Dict, List, Optional

from .generator_common import (
    HTML_FOOTER,
    INHERITABLE_STAMP_FIELDS,
    contains_html,
    extract_image_ocr_data,
    extract_qwen_html,
    format_stamp_parts,
    get_html_header,
    is_image_ocr_json,
    is_qwen_ocr_json,
    sanitize_html,
    strip_code_fence,
)

logger = logging.getLogger(__name__)


# ── Markdown table -> HTML ─────��─────────────────────────────────────

_MD_TABLE_ROW = re.compile(r"^\|(.+)\|$")
_MD_TABLE_SEP = re.compile(r"^\|[\s:]*-{2,}[\s:]*(?:\|[\s:]*-{2,}[\s:]*)*\|$")


def _has_markdown_table(text: str) -> bool:
    """Проверить наличие markdown таблицы (минимум 2 строки с | и разделитель)."""
    lines = text.strip().split("\n")
    pipe_lines = sum(1 for line in lines if _MD_TABLE_ROW.match(line.strip()))
    sep_lines = sum(1 for line in lines if _MD_TABLE_SEP.match(line.strip()))
    return pipe_lines >= 2 and sep_lines >= 1


def _convert_md_table(lines: list) -> str:
    """Конвертировать набор строк markdown таблицы в HTML <table>."""
    rows = []
    is_header = True
    for line in lines:
        if _MD_TABLE_SEP.match(line):
            is_header = False
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        tag = "th" if is_header else "td"
        row_html = "".join(f"<{tag}>{_escape_html(c)}</{tag}>" for c in cells)
        rows.append(f"<tr>{row_html}</tr>")
        if is_header:
            is_header = False

    if not rows:
        return ""

    parts = ["<table>"]
    parts.append(f"<thead>{rows[0]}</thead>")
    if len(rows) > 1:
        parts.append("<tbody>" + "".join(rows[1:]) + "</tbody>")
    parts.append("</table>")
    return "".join(parts)


def _markdown_tables_to_html(text: str) -> str:
    """Конвертировать markdown таблицы в HTML, остальной текст — в <p>."""
    lines = text.strip().split("\n")
    html_parts: list[str] = []
    table_lines: list[str] = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        is_table_line = bool(
            _MD_TABLE_ROW.match(stripped) or _MD_TABLE_SEP.match(stripped)
        )

        if is_table_line:
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(stripped)
        else:
            if in_table:
                html_parts.append(_convert_md_table(table_lines))
                table_lines = []
                in_table = False
            if stripped:
                html_parts.append(f"<p>{_escape_html(stripped)}</p>")

    if in_table and table_lines:
        html_parts.append(_convert_md_table(table_lines))

    return "\n".join(html_parts)


# ── Вспомогательные функции ──────────────────────────────────────────


def _escape_html(text: str) -> str:
    """Экранировать HTML спецсимволы."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _format_stamp_html(stamp_data: Dict) -> str:
    """Форматировать данные штампа в компактный HTML блок."""
    parts = format_stamp_parts(stamp_data)
    if not parts:
        return ""
    html_parts = [f"<b>{key}:</b> {value}" for key, value in parts]
    return '<div class="stamp-info">' + " | ".join(html_parts) + "</div>"


def _format_inherited_stamp_html(inherited_data: Dict) -> str:
    """Форматировать унаследованные данные штампа в компактный HTML блок."""
    parts = []
    if inherited_data.get("document_code"):
        parts.append(f"<b>Шифр:</b> {inherited_data['document_code']}")
    if inherited_data.get("stage"):
        parts.append(f"<b>Стадия:</b> {inherited_data['stage']}")
    if inherited_data.get("project_name"):
        parts.append(f"<b>Объект:</b> {inherited_data['project_name']}")
    if inherited_data.get("organization"):
        parts.append(f"<b>Организация:</b> {inherited_data['organization']}")
    if not parts:
        return ""
    return '<div class="stamp-info stamp-inherited">' + " | ".join(parts) + "</div>"


def _format_image_ocr_html(data: dict) -> str:
    """Форматировать данные OCR изображения в компактный HTML."""
    img_data = extract_image_ocr_data(data)
    parts = []

    # Заголовок: [ИЗОБРАЖЕНИЕ] Тип: XXX | Оси: XXX
    header_parts = ["<b>[ИЗОБРАЖЕНИЕ]</b>"]
    if img_data.get("zone_name") and img_data["zone_name"] != "Не определено":
        header_parts.append(f"Тип: {img_data['zone_name']}")
    if img_data.get("grid_lines") and img_data["grid_lines"] != "Не определены":
        header_parts.append(f"Оси: {img_data['grid_lines']}")
    if img_data.get("location_text"):
        header_parts.append(img_data["location_text"])
    parts.append(f"<p>{' | '.join(header_parts)}</p>")

    if img_data.get("content_summary"):
        parts.append(
            f"<p><b>Краткое описание:</b> {_escape_html(img_data['content_summary'])}</p>"
        )
    if img_data.get("detailed_description"):
        parts.append(
            f"<p><b>Описание:</b> {_escape_html(img_data['detailed_description'])}</p>"
        )
    if img_data.get("clean_ocr_text"):
        parts.append(
            f"<p><b>Текст на чертеже:</b> {_escape_html(img_data['clean_ocr_text'])}</p>"
        )
    if img_data.get("key_entities"):
        entities_str = ", ".join(_escape_html(e) for e in img_data["key_entities"])
        parts.append(f"<p><b>Сущности:</b> {entities_str}</p>")

    return "\n".join(parts) if parts else ""


def _extract_html_from_parsed(data: Any) -> str:
    """Рекурсивно извлечь HTML из распарсенного JSON."""
    html_parts = []
    if isinstance(data, dict):
        if "content_html" in data and isinstance(data["content_html"], str):
            html_parts.append(data["content_html"])
        elif "stamp_html" in data and isinstance(data["stamp_html"], str):
            html_parts.append(data["stamp_html"])
        elif "html" in data and isinstance(data["html"], str):
            html_parts.append(data["html"])
        elif "children" in data and isinstance(data["children"], list):
            for child in data["children"]:
                html_parts.append(_extract_html_from_parsed(child))
    elif isinstance(data, list):
        for item in data:
            html_parts.append(_extract_html_from_parsed(item))
    return "".join(html_parts)


def _extract_html_from_ocr_text(ocr_text: str) -> str:
    """Извлечь HTML из raw OCR текста (pipeline: JSON -> HTML -> MD table -> fallback)."""
    if not ocr_text:
        return ""

    text = strip_code_fence(ocr_text.strip())
    if not text:
        return ""

    # 1. JSON-парсинг (может содержать HTML внутри)
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json_module.loads(text)
            if isinstance(parsed, dict):
                if is_qwen_ocr_json(parsed):
                    html = extract_qwen_html(parsed)
                    return sanitize_html(html) if html else ""
                if is_image_ocr_json(parsed):
                    formatted = _format_image_ocr_html(parsed)
                    if formatted:
                        return formatted
                html = _extract_html_from_parsed(parsed)
                if html:
                    return sanitize_html(html)
        except json_module.JSONDecodeError:
            pass

    # 2. Чистый HTML
    if contains_html(text):
        return sanitize_html(text)

    # 3. Markdown таблица -> HTML
    if _has_markdown_table(text):
        return _markdown_tables_to_html(text)

    # 4. Fallback: plain text
    return f"<pre>{_escape_html(text)}</pre>"


def _extract_block_content_html(block: Dict) -> str:
    """Извлечь HTML контент из блока (приоритет: render_html -> structured_json -> text).

    Это основной pipeline для web MVP — использует current state из БД.
    """
    # Приоритет 1: готовый HTML от recognition
    render_html = block.get("current_render_html")
    if render_html and render_html.strip():
        return sanitize_html(render_html)

    # Приоритет 2: structured JSON
    structured = block.get("current_structured_json")
    if isinstance(structured, dict) and structured:
        if is_qwen_ocr_json(structured):
            html = extract_qwen_html(structured)
            if html:
                return sanitize_html(html)
        if is_image_ocr_json(structured):
            formatted = _format_image_ocr_html(structured)
            if formatted:
                return formatted

    # Приоритет 3: raw text (legacy pipeline)
    current_text = block.get("current_text")
    if current_text and current_text.strip():
        return _extract_html_from_ocr_text(current_text)

    return ""


# ── Основная функция генерации ─────��─────────────────────────────────


def generate_html(
    blocks: List[Dict],
    doc_title: str,
    inherited_stamp: Optional[Dict],
    page_stamps: Dict[int, Optional[Dict]],
    crop_urls: Dict[str, str],
    options: Dict,
) -> str:
    """Сгенерировать итоговый HTML документ из отсортированных блоков.

    Args:
        blocks: отсортированные блоки (dict из Supabase)
        doc_title: заголовок документа
        inherited_stamp: общие наследуемые поля штампа (мода)
        page_stamps: {page_number: stamp_data или None} для каждой страницы
        crop_urls: {block_id: presigned URL} для crop изображений
        options: include_crop_links, include_stamp_info

    Returns:
        Строка с HTML документом
    """
    include_crop_links = options.get("include_crop_links", True)
    include_stamp_info = options.get("include_stamp_info", True)

    # Предвычисляем stamp HTML для inherited
    inherited_stamp_html = (
        _format_inherited_stamp_html(inherited_stamp)
        if include_stamp_info and inherited_stamp
        else ""
    )

    html_parts = [get_html_header(doc_title)]

    block_count = 0

    # Группировка по page_number
    for page_num, page_blocks_iter in groupby(blocks, key=lambda b: b["page_number"]):
        page_blocks = list(page_blocks_iter)
        display_page = page_num + 1 if page_num is not None else 0

        html_parts.append(f"<h2>Страница {display_page}</h2>")

        # Stamp info для страницы
        if include_stamp_info:
            page_stamp = page_stamps.get(page_num)
            if page_stamp:
                # Мержим с inherited: пустые поля заполняем из inherited
                merged_stamp = dict(page_stamp)
                if inherited_stamp:
                    for field in INHERITABLE_STAMP_FIELDS:
                        if not merged_stamp.get(field) and inherited_stamp.get(field):
                            merged_stamp[field] = inherited_stamp[field]
                stamp_html = _format_stamp_html(merged_stamp)
            elif inherited_stamp:
                stamp_html = inherited_stamp_html
            else:
                stamp_html = ""
        else:
            stamp_html = ""

        for block in page_blocks:
            # Пропускаем stamp блоки (они уже отображены как метаданные)
            if block.get("block_kind") == "stamp":
                continue

            block_count += 1
            block_kind = block.get("block_kind", "text")
            block_id = block.get("id", "")

            html_parts.append(f'<div class="block block-type-{block_kind}">')
            html_parts.append(
                f'<div class="block-header">'
                f"Блок #{block_count} (стр. {display_page}) | "
                f"Тип: {block_kind} | ID: {block_id[:8]}"
                f"</div>"
            )
            html_parts.append('<div class="block-content">')

            # Stamp info в блоке
            if stamp_html:
                html_parts.append(stamp_html)

            # Crop link
            if include_crop_links and block_id in crop_urls:
                url = crop_urls[block_id]
                html_parts.append(
                    f'<p><a href="{url}" target="_blank">'
                    f"<b>Открыть кроп изображения</b></a></p>"
                )

            # Контент блока
            content_html = _extract_block_content_html(block)
            if content_html:
                html_parts.append(content_html)

            html_parts.append("</div></div>")

    html_parts.append(HTML_FOOTER)

    logger.info("HTML export сгенерирован: %d ��локов", block_count)
    return "\n".join(html_parts)
