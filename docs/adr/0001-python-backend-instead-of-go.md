# ADR-0001: Python backend вместо Go

> Дата: 2026-04-05
> Статус: Принят

## Контекст

Legacy backend OCR-системы написан на Python (FastAPI + Celery). Ключевые переиспользуемые модули:

- `StreamingPDFProcessor` (PyMuPDF/fitz) — crop/render PDF, ~300 строк проверенного кода
- `OpenRouterBackend` — адаптер к OpenRouter API с retry session, media encoding, model list caching
- `ChandraBackend` — адаптер к LM Studio с model discovery, preload, time budget detection
- `CircuitBreaker` — state machine CLOSED/OPEN/HALF_OPEN для защиты от перегрузки
- `block_verification` — post-OCR retry missing/suspicious блоков с fallback chain
- `text_ocr_quality` — классификация качества OCR (empty/error/suspicious/ok)
- `backend_factory` — фабрика OCR бэкендов с fallback chain (Chandra → Datalab → OpenRouter)
- `html_generator`, `md/generator` — export в HTML и Markdown

Все эти модули используют Python-specific библиотеки: PyMuPDF (C-extension для PDF), Pillow (image processing), requests/httpx (HTTP clients).

При переходе на Go потребуется:
- Полное переписывание OCR pipeline (~2000+ строк)
- Поиск/написание Go-binding для PyMuPDF (не существует production-ready)
- Переписывание image processing (Pillow → Go image library)
- Потеря проверенной retry/fallback логики

## Решение

Python (FastAPI) для backend. Без Celery — async native через asyncio. Модули адаптируются (thread → async), не переписываются.

Ключевые адаптации:
- `threading.Lock` → `asyncio.Lock` (circuit_breaker)
- `requests.Session` → `httpx.AsyncClient` (OCR adapters)
- Celery tasks → `asyncio.create_task()` + FastAPI background tasks
- Sync context manager → async context manager (StreamingPDFProcessor)

## Последствия

### Положительные
- 70%+ кода OCR pipeline переиспользуется с минимальной адаптацией
- Единый язык для PDF processing — PyMuPDF нативно поддерживается
- FastAPI нативно поддерживает async, SSE, OpenAPI docs, Pydantic validation
- Команда имеет экспертизу в Python и знание legacy кода

### Отрицательные
- Python медленнее Go для CPU-bound операций
- GIL ограничивает параллелизм CPU-bound задач
- Для web MVP это приемлемо: bottleneck — LLM API latency (секунды), не Python (миллисекунды)

### Риски
- GIL для CPU-bound crop → Mitigation: PyMuPDF рендерит через C-extension, Pillow — через libpng/libjpeg. Реальная работа за GIL.
- Память при обработке больших PDF → Mitigation: StreamingPDFProcessor обрабатывает по одной странице, освобождает предыдущую

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Go + переписывание OCR | 3-4x больше effort, нет production-ready PyMuPDF binding для Go |
| Node.js backend | Нет PyMuPDF, нет legacy code reuse, нет Pillow |
| Python + Go microservice для crop | Overengineering для MVP, усложняет deploy |
| Rust backend | Максимальный effort, нет legacy reuse, нет экспертизы |
