# ADR-0005: Локальный crop runtime и финальный R2 upload

> Дата: 2026-04-05
> Статус: Принят

## Контекст

### Как работают кропы в legacy

`StreamingPDFProcessor` из `pdf_streaming_core.py` вырезает блоки из PDF:
1. Открывает PDF через PyMuPDF (`fitz.open()`)
2. Рендерит страницу в PIL Image с учётом zoom
3. Вырезает crop по координатам блока (`crop_block_image()`)
4. Для IMAGE блоков: также сохраняет PDF crop (`crop_block_to_pdf()`)

### Промежуточные кропы в R2 (legacy)

`task_upload.py` загружает кропы в R2 во время OCR обработки:

```
Pass 1 (crop):
  PDF → strips (PNG) → сохранение на диск
  PDF → image crops (PNG + PDF) → сохранение на диск

Pass 2 (OCR):
  Чтение strips/crops с диска → отправка в LLM API

Upload (post-OCR):
  strips/* → R2  (промежуточные, не нужны после)
  images/* → R2  (промежуточные + финальные)
  annotation.json → R2
  result.json → R2
  ocr_result.html → R2
  document.md → R2
```

### Проблемы legacy подхода

1. **Network overhead**: каждый crop = HTTP PUT к R2 (~100ms per file). Документ с 50 блоками = 50 HTTP запросов только для upload
2. **R2 dependency**: если R2 недоступен во время OCR → pipeline зависает
3. **Storage cost**: промежуточные strips остаются в R2 навсегда (нет cleanup)
4. **Complexity**: `task_upload.py` — 200+ строк для управления upload/cleanup
5. **Дублирование**: annotation.json и result.json в R2 дублируют данные из Postgres

### Кто потребляет кропы

- **OCR backend** (Chandra, OpenRouter) — получает crop как base64 image → нужен только на backend
- **Frontend UI** — показывает crop для image/stamp блоков → нужен persistent URL
- **Export HTML** — ссылка на crop в `<img src="...">` → нужен persistent URL

## Решение

### Runtime: кропы в /tmp на backend

```
OCR pipeline:
  1. Download PDF from R2 (один раз, кэшируется)
  2. Для каждого блока:
     a. crop = StreamingPDFProcessor.crop_block_image(block)
        → PIL Image в памяти или /tmp/ocr_{run_id}/{block_id}.png
     b. result = ocr_backend.recognize(crop, prompt)
        → crop передаётся как bytes/base64, не через R2
     c. if success AND block_kind IN ('image', 'stamp'):
        → upload final crop to R2
        → UPDATE blocks SET r2_crop_key = ...
     d. delete local crop file
  3. rm -rf /tmp/ocr_{run_id}/
```

### Что хранится в R2

| Файл | Когда загружается | Для чего |
|------|------------------|---------|
| Original PDF | При upload документа (один раз) | Viewer, повторный crop при rerun |
| Финальный crop (image/stamp) | После успешного OCR блока | Отображение в UI, export HTML |

### Что НЕ хранится в R2

| Файл (legacy) | Почему убрано |
|----------------|--------------|
| Промежуточные strip кропы | Strips удалены из архитектуры (per-block OCR) |
| Кропы text блоков | Текст сохранён в Postgres, визуальный crop не нужен |
| annotation.json | State в Postgres (ADR-0004) |
| result.json | State в Postgres (ADR-0004) |
| ocr_result.html | Генерируется on-demand из Postgres |
| document.md | Генерируется on-demand из Postgres |

### R2 key structure

```
documents/{user_id}/{document_id}.pdf          # original PDF
crops/{document_id}/{block_id}.pdf             # финальный crop (image/stamp)
```

## Последствия

### Положительные
- **Нет network overhead**: crop → OCR backend всё в памяти/localhost
- **Нет R2 dependency во время OCR**: R2 нужен только для скачивания PDF (один раз) и финального upload
- **Меньше storage**: нет strips, промежуточных кропов, дубликатов annotation/result
- **Простой cleanup**: `rm -rf /tmp/ocr_{run_id}/` после завершения
- **Быстрее**: нет 50 HTTP PUT запросов, только 1 GET (PDF) + N PUT (финальные crops)

### Отрицательные
- **Disk space на backend**: нужно ~100MB temp space для больших PDF (mitigation: последовательная обработка + cleanup после каждого блока)
- **Нет возможности resume с другого сервера**: промежуточные crop-ы не персистентны (mitigation: для MVP один backend сервер)
- **Text блоки без визуального crop**: пользователь не видит "что именно модель увидела" (mitigation: PDF viewer показывает блок на странице)

### Требования к backend серверу
- Disk: ~500MB temp space (достаточно для 5 concurrent OCR runs)
- Cleanup cron: удалять `/tmp/ocr_*` старше 1 часа (страховка от leaked files)

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Все кропы в R2 (как legacy) | Network overhead, R2 dependency, storage cost |
| Все кропы в Postgres (bytea) | DB bloat, медленные query, VACUUM pressure |
| Redis для промежуточных кропов | Overengineering, memory pressure, unnecessary complexity |
| S3 presigned upload → OCR backend reads from S3 | Extra hop, latency, R2 dependency |
