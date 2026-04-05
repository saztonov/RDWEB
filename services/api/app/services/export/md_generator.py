"""Генератор Markdown документа из текущего состояния блоков в БД.

Адаптация legacy rd_core/ocr/md/ (generator.py + formatter.py + html_converter.py + table_converter.py).
Source of truth — PostgreSQL (current_render_html, current_structured_json, current_text).
"""
import json as json_module
import logging
import re
from datetime import datetime, timezone
from itertools import groupby
from typing import Any, Dict, List, Optional

from .generator_common import (
    DATALAB_MD_IMG_PATTERN,
    INHERITABLE_STAMP_FIELDS,
    contains_html,
    extract_image_ocr_data,
    extract_qwen_html,
    format_stamp_parts,
    is_image_ocr_json,
    is_qwen_ocr_json,
    sanitize_html,
    sanitize_markdown,
    strip_code_fence,
)

logger = logging.getLogger(__name__)


# ── HTML table -> Markdown table ─────────────────────────────────────


def _clean_cell_text(text: str) -> str:
    """Очистить текст ячейки таблицы."""
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _parse_cell_span(cell_tag: str) -> tuple:
    """Извлечь colspan и rowspan из тега ячейки."""
    colspan_match = re.search(r"colspan\s*=\s*[\"']?(\d+)", cell_tag, re.IGNORECASE)
    rowspan_match = re.search(r"rowspan\s*=\s*[\"']?(\d+)", cell_tag, re.IGNORECASE)
    colspan = int(colspan_match.group(1)) if colspan_match else 1
    rowspan = int(rowspan_match.group(1)) if rowspan_match else 1
    return colspan, rowspan


def _table_to_markdown(table_html: str) -> str:
    """Конвертировать HTML таблицу в Markdown (поддержка colspan/rowspan)."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, flags=re.DOTALL)
    if not rows:
        return ""

    parsed_rows: list[list[str]] = []
    rowspan_tracker: dict[int, tuple[int, str]] = {}

    for row_html in rows:
        cell_matches = re.findall(
            r"<(t[hd][^>]*)>(.*?)</t[hd]>", row_html, flags=re.DOTALL
        )
        if not cell_matches:
            continue

        row_cells: list[str] = []
        col_idx = 0
        cell_iter = iter(cell_matches)

        while True:
            if col_idx in rowspan_tracker:
                remaining, _text = rowspan_tracker[col_idx]
                row_cells.append("")
                if remaining <= 1:
                    del rowspan_tracker[col_idx]
                else:
                    rowspan_tracker[col_idx] = (remaining - 1, _text)
                col_idx += 1
                continue

            try:
                cell_tag, cell_content = next(cell_iter)
            except StopIteration:
                break

            colspan, rowspan = _parse_cell_span(cell_tag)
            text = re.sub(r"<br\s*/?>", " ", cell_content, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)
            text = _clean_cell_text(text)

            row_cells.append(text)

            if rowspan > 1:
                rowspan_tracker[col_idx] = (rowspan - 1, text)

            col_idx += 1

            for _ in range(colspan - 1):
                row_cells.append("")
                col_idx += 1

        while col_idx in rowspan_tracker:
            remaining, _text = rowspan_tracker[col_idx]
            row_cells.append("")
            if remaining <= 1:
                del rowspan_tracker[col_idx]
            else:
                rowspan_tracker[col_idx] = (remaining - 1, _text)
            col_idx += 1

        if row_cells:
            parsed_rows.append(row_cells)

    if not parsed_rows:
        return ""

    max_cols = max(len(row) for row in parsed_rows)
    for row in parsed_rows:
        while len(row) < max_cols:
            row.append("")

    md_rows = []
    for i, row in enumerate(parsed_rows):
        escaped_cells = [cell.replace("|", "\\|") for cell in row]
        md_rows.append("| " + " | ".join(escaped_cells) + " |")
        if i == 0:
            md_rows.append("|" + "|".join(["---"] * max_cols) + "|")

    return "\n".join(md_rows)


# ── HTML -> Markdown ─────────────────────────────────────────────────


def _html_to_markdown(html: str) -> str:
    """Конвертировать HTML в компактный Markdown."""
    if not html:
        return ""

    text = sanitize_html(html)

    # Удаляем stamp-info блоки (уже в header)
    text = re.sub(
        r'<div class="stamp-info[^"]*">.*?</div>', "", text, flags=re.DOTALL
    )

    # Удаляем BLOCK маркеры и метаданные
    text = re.sub(r"<p>BLOCK:\s*[A-Z0-9\-]+</p>", "", text)
    text = re.sub(r"<p><b>Created:</b>[^<]*</p>", "", text)
    text = re.sub(r"<p><b>Linked block:</b>[^<]*</p>", "", text)
    text = re.sub(r"<p><b>Grouped blocks:</b>[^<]*</p>", "", text)

    # Удаляем ссылки на кроп изображения
    text = re.sub(
        r"<p><a[^>]*>.*?Открыть кроп изображения.*?</a></p>",
        "",
        text,
        flags=re.DOTALL,
    )

    # Таблицы ПЕРЕД остальным HTML
    def _process_table(match: re.Match) -> str:
        return _table_to_markdown(match.group(0))

    text = re.sub(
        r"<table[^>]*>.*?</table>", _process_table, text, flags=re.DOTALL
    )

    # Заголовки (сдвиг на 3 уровня вниз для вложенности)
    text = re.sub(r"<h1[^>]*>\s*(.*?)\s*</h1>", r"#### \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<h2[^>]*>\s*(.*?)\s*</h2>", r"##### \1\n", text, flags=re.DOTALL)
    text = re.sub(
        r"<h3[^>]*>\s*(.*?)\s*</h3>", r"###### \1\n", text, flags=re.DOTALL
    )
    text = re.sub(
        r"<h4[^>]*>\s*(.*?)\s*</h4>", r"###### \1\n", text, flags=re.DOTALL
    )

    # Форматирование
    text = re.sub(r"<b>\s*(.*?)\s*</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<strong>\s*(.*?)\s*</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<i>\s*(.*?)\s*</i>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<em>\s*(.*?)\s*</em>", r"*\1*", text, flags=re.DOTALL)

    # Код
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    text = re.sub(r"<pre[^>]*>(.*?)</pre>", r"```\n\1\n```", text, flags=re.DOTALL)

    # Списки
    text = re.sub(r"<li>\s*(.*?)\s*</li>", r"- \1\n", text, flags=re.DOTALL)
    text = re.sub(r"<[ou]l[^>]*>", "", text)
    text = re.sub(r"</[ou]l>", "", text)

    # Удаляем img теги
    text = re.sub(r"<img[^>]*/?>", "", text)

    # Ссылки
    text = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL
    )

    # Переносы строк и параграфы
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<p[^>]*>\s*(.*?)\s*</p>", r"\1\n", text, flags=re.DOTALL)

    # Удаляем оставшиеся HTML теги
    text = re.sub(r"<[^>]+>", "", text)

    # Декодируем HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    # Удаляем мусорные markdown-ссылки на изображения
    text = DATALAB_MD_IMG_PATTERN.sub("", text)

    # Нормализуем пробелы
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ── Форматирование stamp/image для MD ───────────────────────────────


def _format_stamp_md(stamp_data: Dict) -> str:
    """Форматировать данные штампа в компактную Markdown строку."""
    parts = []
    if stamp_data.get("document_code"):
        parts.append(f"Шифр: {stamp_data['document_code']}")
    if stamp_data.get("stage"):
        parts.append(f"Стадия: {stamp_data['stage']}")
    if stamp_data.get("project_name"):
        parts.append(f"Объект: {stamp_data['project_name']}")
    if stamp_data.get("organization"):
        parts.append(f"Организация: {stamp_data['organization']}")
    return " | ".join(parts) if parts else ""


def _format_image_ocr_md(data: dict) -> str:
    """Форматировать данные OCR изображения в компактный Markdown."""
    img_data = extract_image_ocr_data(data)
    parts = []

    header_parts = ["**[ИЗОБРАЖЕНИЕ]**"]
    if img_data.get("zone_name") and img_data["zone_name"] != "Не определено":
        header_parts.append(f"Тип: {img_data['zone_name']}")
    if img_data.get("grid_lines") and img_data["grid_lines"] != "Не определены":
        header_parts.append(f"Оси: {img_data['grid_lines']}")
    if img_data.get("location_text"):
        header_parts.append(img_data["location_text"])
    parts.append(" | ".join(header_parts))

    if img_data.get("content_summary"):
        parts.append(f"**Краткое описание:** {img_data['content_summary']}")
    if img_data.get("detailed_description"):
        parts.append(f"**Описание:** {img_data['detailed_description']}")
    if img_data.get("clean_ocr_text"):
        parts.append(f"**Текст на чертеже:** {img_data['clean_ocr_text']}")
    if img_data.get("key_entities"):
        entities = ", ".join(img_data["key_entities"])
        parts.append(f"**Сущности:** {entities}")

    return "\n".join(parts) if parts else ""


def _process_ocr_content(ocr_text: str) -> str:
    """Обработать raw OCR текст и конвертировать в Markdown."""
    if not ocr_text:
        return ""

    text = strip_code_fence(ocr_text.strip())
    if not text:
        return ""

    # 1. JSON
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json_module.loads(text)
            if isinstance(parsed, dict):
                if is_qwen_ocr_json(parsed):
                    html = extract_qwen_html(parsed)
                    return _html_to_markdown(html) if html else ""
                if is_image_ocr_json(parsed):
                    return _format_image_ocr_md(parsed)
            return json_module.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except json_module.JSONDecodeError:
            pass

    # 2. HTML контент
    if contains_html(text):
        return _html_to_markdown(text)

    # 3. Обычный текст
    return sanitize_markdown(text)


def _extract_block_content_md(block: Dict) -> str:
    """Извлечь Markdown контент из блока (приоритет: render_html -> structured_json -> text).

    Это основной pipeline для web MVP — использует current state из БД.
    """
    # Приоритет 1: готовый HTML от recognition -> конвертируем в MD
    render_html = block.get("current_render_html")
    if render_html and render_html.strip():
        return _html_to_markdown(render_html)

    # Приоритет 2: structured JSON
    structured = block.get("current_structured_json")
    if isinstance(structured, dict) and structured:
        if is_qwen_ocr_json(structured):
            html = extract_qwen_html(structured)
            if html:
                return _html_to_markdown(html)
        if is_image_ocr_json(structured):
            formatted = _format_image_ocr_md(structured)
            if formatted:
                return formatted

    # Приоритет 3: raw text
    current_text = block.get("current_text")
    if current_text and current_text.strip():
        return _process_ocr_content(current_text)

    return ""


# ── Основная функция генерации ───────────────────────────────────────


def generate_markdown(
    blocks: List[Dict],
    doc_title: str,
    inherited_stamp: Optional[Dict],
    page_stamps: Dict[int, Optional[Dict]],
    crop_urls: Dict[str, str],
    options: Dict,
) -> str:
    """Сгенерировать итоговый Markdown документ из отсортированных блоков.

    Args:
        blocks: отсортированные блоки (dict из Supabase)
        doc_title: заголовок документа
        inherited_stamp: общие наследуемые поля штампа (мода)
        page_stamps: {page_number: stamp_data или None} для каждой страницы
        crop_urls: {block_id: presigned URL} для crop изображений
        options: include_crop_links, include_stamp_info

    Returns:
        Строка с Markdown документом
    """
    include_crop_links = options.get("include_crop_links", True)
    include_stamp_info = options.get("include_stamp_info", True)

    md_parts: list[str] = []

    # === HEADER ===
    md_parts.append(f"# {doc_title}")
    md_parts.append("")
    md_parts.append(
        f"Сгенерировано: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    # Штамп документа
    if include_stamp_info and inherited_stamp:
        stamp_str = _format_stamp_md(inherited_stamp)
        if stamp_str:
            md_parts.append(f"**Штамп:** {stamp_str}")

    md_parts.append("")
    md_parts.append("---")
    md_parts.append("")

    # === БЛОКИ — группировка по страницам ===
    block_count = 0

    for page_num, page_blocks_iter in groupby(blocks, key=lambda b: b["page_number"]):
        page_blocks = list(page_blocks_iter)
        display_page = page_num + 1 if page_num is not None else 0

        # Проверяем есть ли non-stamp блоки
        non_stamp_blocks = [
            b for b in page_blocks if b.get("block_kind") != "stamp"
        ]
        if not non_stamp_blocks:
            continue

        # Заголовок страницы
        md_parts.append(f"## СТРАНИЦА {display_page}")

        # Информация из штампа страницы (лист, наименование)
        if include_stamp_info:
            page_stamp = page_stamps.get(page_num)
            if page_stamp:
                sheet_num = page_stamp.get("sheet_number", "")
                total_sheets = page_stamp.get("total_sheets", "")
                sheet_name = page_stamp.get("sheet_name", "")

                if sheet_num or total_sheets:
                    if total_sheets:
                        md_parts.append(f"**Лист:** {sheet_num} (из {total_sheets})")
                    else:
                        md_parts.append(f"**Лист:** {sheet_num}")

                if sheet_name:
                    md_parts.append(f"**Наименование листа:** {sheet_name}")

        md_parts.append("")

        for block in page_blocks:
            # Пропускаем stamp блоки
            if block.get("block_kind") == "stamp":
                continue

            block_count += 1
            block_kind = block.get("block_kind", "text").upper()
            block_id = block.get("id", "")

            # Заголовок блока
            md_parts.append(f"### BLOCK [{block_kind}]: {block_id[:8]}")

            # Stamp info
            if include_stamp_info:
                page_stamp = page_stamps.get(page_num)
                if page_stamp:
                    merged = dict(page_stamp)
                    if inherited_stamp:
                        for field in INHERITABLE_STAMP_FIELDS:
                            if not merged.get(field) and inherited_stamp.get(field):
                                merged[field] = inherited_stamp[field]
                    stamp_str = _format_stamp_md(merged)
                    if stamp_str:
                        md_parts.append(f"**Штамп:** {stamp_str}")
                elif inherited_stamp:
                    stamp_str = _format_stamp_md(inherited_stamp)
                    if stamp_str:
                        md_parts.append(f"**Штамп:** {stamp_str}")

            # Crop link
            if include_crop_links and block_id in crop_urls:
                url = crop_urls[block_id]
                md_parts.append(f"[Открыть кроп изображения]({url})")

            # Контент блока
            content = _extract_block_content_md(block)
            if content:
                md_parts.append(content)
            else:
                md_parts.append("*(нет данных)*")

            md_parts.append("")

    logger.info("MD export сгенерирован: %d блоков", block_count)
    return "\n".join(md_parts)
