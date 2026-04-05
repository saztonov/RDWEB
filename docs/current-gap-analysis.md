# GAP-анализ: Legacy Desktop → Web MVP

> Дата: 2026-04-05  
> Статус: Утверждён  
> Версия: 1.0

## A. Таблица OLD → NEW по подсистемам

### 1. Block Model

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Типы блоков | `BlockType`: TEXT, IMAGE. Table конвертируется в TEXT при десериализации (`block.py:244`: `if raw_type == "table": block_type = BlockType.TEXT`) | `BlockKind`: text, stamp, image. Table удалён полностью |
| Stamp | IMAGE + `category_code="stamp"`. Условные проверки в 5+ местах (task_upload, backend_factory, export, verification, job_settings) | Отдельный first-class kind `stamp` |
| Хранение | In-memory dataclass, сериализуется в `annotations.data` JSONB blob (один blob на документ) | Строка в таблице `blocks` (одна строка = один блок) |
| Идентификатор | Armor ID (`XXXX-XXXX-XXX`) + legacy UUID миграция | UUID primary key + armor_id (UNIQUE, для display) |
| Координаты | `coords_px` + `coords_norm` (tuple), конвертация через `px_to_norm()`/`norm_to_px()` | `coords_px INTEGER[4]` + `coords_norm FLOAT[4]` в Postgres |
| Форма | `ShapeType`: RECTANGLE, POLYGON. `polygon_points` как список tuple | `shape_type` CHECK + `polygon_points` JSONB |
| Промпт | `prompt` dict `{system, user}` хранится внутри блока | Промпт НЕ хранится в блоке — берётся из таблицы `prompts` |
| Коррекция | `is_correction` флаг на блоке | `is_dirty` флаг + `attempt_number` в `ocr_results` |
| Связи | `linked_block_id` (image → text) | `linked_block_id` FK → `blocks(id)` |
| Тип изменения | **Breaking change + schema migration** | |

### 2. Prompt Model

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Источники | 3 конкурирующих: (a) `block.prompt` dict, (b) `config.yaml` через `storage_settings.py`, (c) `image_categories` таблица | Единственный: таблица `prompts` в Postgres |
| Приоритет | `block.prompt` > category > config.yaml default (`worker_prompts.py::get_image_block_prompt()`) | Lookup: `WHERE block_kind + category_code + engine`, fallback через `IS NULL` |
| Переменные | `{DOC_NAME}`, `{PAGE_NUM}`, `{BLOCK_ID}`, `{OPERATOR_HINT}`, `{PDFPLUMBER_TEXT}` через `fill_image_prompt_variables()` | Те же переменные, тот же substitution pattern |
| Управление | Редактирование config.yaml + redeploy | Admin UI + API `PATCH /api/prompts/{id}` без redeploy |
| Версионирование | Нет | `version INTEGER` в таблице `prompts` |
| Seed данные | Hardcoded в config.yaml | SQL миграция с INSERT seed данных |
| Тип изменения | **Полная замена** | |

### 3. OCR Pipeline

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Архитектура | Two-pass: Pass1 (crop → strip merge → manifest), Pass2 (async strip OCR) | Per-block: crop одного блока → OCR одного блока → результат в Postgres |
| Группировка | TEXT блоки объединяются в strips (`pass1_crops.py::_group_and_merge_strips()`) с BLOCK-разделителями | Каждый блок обрабатывается отдельно, нет strips |
| Batch parsing | `parse_batch_response_by_block_id()` — fuzzy matching armor ID в ответе | Ответ = один блок, parsing тривиален |
| Task runner | Celery + Redis (prefork workers) | FastAPI async background tasks |
| Checkpoint | Файловый checkpoint на диске | `ocr_results` таблица + `ocr_runs.processed_blocks` |
| Прогресс | Debounced DB update (`debounced_updater.py`) | SSE endpoint `/api/ocr/runs/{id}/progress` |
| Smart rerun | Нет (полный rerun) | Только `is_dirty=true` блоки; skip `is_manual_edit=true` |
| Отмена | `should_stop()` callback + Redis | `POST /api/ocr/runs/{id}/cancel` + asyncio.Event |
| Тип изменения | **Фундаментальная переработка** | |

### 4. Storage Model

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| R2 содержимое | original PDF, annotation.json, result.json, result_md, ocr_html, все кропы (strips, images, промежуточные) | ТОЛЬКО: original PDF + финальный crop блока (image/stamp) |
| Промежуточные кропы | Загружаются в R2 через `task_upload.py` во время OCR | Живут в `/tmp` на backend, удаляются после OCR |
| Source of truth | Два конкурирующих: `annotations.data` JSONB blob + `result.json` в R2 | Единственный: Postgres (таблицы `blocks`, `ocr_results`) |
| Merge | `ocr_result_merger.py` мержит annotation.json + ocr_html → result.json | Нет merge — данные нормализованы в отдельных таблицах |
| Файловые типы | `job_files` + `node_files` (два каталога файлов) | Один `r2_crop_key` на блоке + `r2_key` на документе |
| Cleanup | Сложный — нужно удалять strips, промежуточные кропы, old results | Простой — `rm -rf /tmp/ocr_{run_id}/` |
| Тип изменения | **Архитектурная инверсия** | |

### 5. Export Model

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| HTML | `html_generator.py` — monolithic HTML с inline styles | Адаптация: читает из Postgres вместо in-memory/result.json |
| Markdown | `md/generator.py` — optimized для LLM | Адаптация: `SELECT blocks JOIN ocr_results` → генерация |
| Источник данных | Document/Page/Block in-memory объекты ИЛИ result.json | `SELECT` из Postgres с JOIN |
| Stamp inheritance | `generator_common.py` — наследование полей штампа на страницы | Сохраняется: stamp `ocr_json` → header документа |
| Crop URLs | `{R2_PUBLIC_URL}/tree_docs/{id}/crops/{block_id}.pdf` | Presigned URL из R2 через backend proxy |
| Форматы | HTML, MD, result.json | HTML, MD (result.json убран — всё в Postgres) |
| Тип изменения | **Адаптация** | |

### 6. Retry / Fallback Model

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Уровень retry | Strip-level (один strip = несколько блоков) | Per-block (один retry = один блок) |
| Verification | `block_verification.py` — post-OCR scan missing/suspicious blocks | Адаптация: `SELECT blocks WHERE quality_score IN ('suspicious','error')` |
| Quality classifier | `text_ocr_quality.py::classify_text_output()` — empty/error/suspicious/ok | Переиспользуется с адаптацией |
| Circuit breaker | `circuit_breaker.py` — CLOSED/OPEN/HALF_OPEN, thread-safe | Переиспользуется: `asyncio.Lock` вместо `threading.Lock` |
| Backend factory | `backend_factory.py::JobBackends` — strip/image/stamp + text_fallback | Адаптация: text/image/stamp (нет strip), fallback сохраняется |
| Fallback chain | Chandra → Datalab → OpenRouter | Chandra → OpenRouter (Datalab по конфигу) |
| Budget exhausted | Chandra-specific: 3× budget exhausted → switch to fallback permanently | Сохраняется в адаптированном виде |
| Consecutive failures | 10 consecutive → wait for backend (LM Studio) or abort | Сохраняется |
| Тип изменения | **Упрощение + адаптация** | |

### 7. Auth / User Ownership

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Идентификация | `client_id` из файла `~/.config/CoreStructure/client_id.txt` | Supabase Auth (email/password + OAuth) |
| Авторизация | Нет (все данные доступны всем) | RLS-policies на уровне Postgres |
| Привязка данных | `jobs.client_id`, `tree_nodes.client_id` | `documents.user_id`, `ocr_runs.user_id` → `auth.users(id)` |
| API ключи | На desktop клиенте (Supabase anon key, R2 credentials) | Только на backend, frontend получает JWT |
| Секреты | В `.env` файле desktop приложения | Backend `settings.py` / env vars, frontend не имеет секретов |
| Тип изменения | **Новая подсистема** | |

### 8. Admin / Ops

| Аспект | OLD (legacy) | NEW (web MVP) |
|--------|-------------|---------------|
| Health | `/health` endpoint (basic) | Health dashboard: Backend, LM Studio, R2, Supabase, OpenRouter + CircuitBreaker state |
| Logging | `logging_config.py` — JSON structured + text mode | Сохраняется JSON формат, те же extra fields |
| Events | Нет таблицы events | Таблица `events` (event_type, severity, payload JSONB) |
| Admin UI | Нет | 5 панелей: health, sources, runs, incidents, events |
| Monitoring | Celery signals | SSE + polling admin endpoints |
| Incident tracking | Нет | Block incidents: quality_score='suspicious'/'error', группировка по документу |
| Тип изменения | **Новая подсистема** | |

---

## B. Архитектурные фиксации

### 1. Почему table удаляется полностью

В legacy `table` уже является мёртвым кодом. В `block.py:244`:
```python
if raw_type == "table":
    block_type = BlockType.TEXT
```

Table конвертируется в TEXT при десериализации. Нет отдельной OCR логики для таблиц — они распознаются теми же моделями, что и text. Поле `table_model` в `job_settings` существует, но используется как alias для text модели. LLM-модели (Qwen, Claude, GPT) естественно распознают таблицы в текстовом выводе (HTML `<table>` или Markdown).

Поддержка table в enum, БД, API, UI, queue names и export logic — это мёртвый код, который усложняет систему без добавления ценности.

### 2. Почему stamp становится отдельным типом

В legacy stamp реализован как `IMAGE` + `category_code="stamp"`. Это создаёт условные проверки в 5+ местах:

- `task_upload.py:42` — исключение stamp из crop upload
- `backend_factory.py:29` — отдельный `stamp_backend` в `JobBackends`
- `job_settings` — отдельное поле `stamp_model`
- `html_generator.py` — специальное форматирование stamp_data
- `block_verification.py` — пропуск stamp блоков при verification

Stamp имеет уникальную семантику: наследование полей (шифр, стадия, организация) на все страницы, специальный промпт, специальный экспорт. Отдельный `block_kind='stamp'` устраняет все `if category_code == "stamp"` проверки и делает типизацию честной.

### 3. Почему промпты только из БД

В legacy промпты разбросаны по трём источникам с приоритетной цепочкой:

1. `block.prompt` dict на самом блоке (сериализуется в annotations.data JSONB)
2. `config.yaml` через `storage_settings.py::get_category_prompt()` — hardcoded в файле
3. `image_categories` таблица в БД — `system_prompt`, `user_prompt` по category code

`worker_prompts.py::get_image_block_prompt()` реализует приоритет: block.prompt > category > config default.

Проблемы: дрейф между config.yaml и БД, невозможность обновить промпт без redeploy, невозможность отследить "какой промпт использовался для этого блока".

Единая таблица `prompts` с полями `block_kind`, `category_code`, `engine`, `version` устраняет все эти проблемы. Lookup простой: `WHERE block_kind = $1 AND (category_code = $2 OR category_code IS NULL) AND (engine = $3 OR engine IS NULL)`.

### 4. Почему result.json и annotations blob не подходят для web

**annotations.data JSONB blob:**
- Весь state блоков документа в одном поле
- Любое обновление одного блока → перезапись всего blob
- Race condition при параллельном редактировании
- Невозможность гранулярных query (`WHERE quality = 'suspicious'`)
- Нет транзакций на уровне блоков
- Три версии формата (v0, v1, v2) с миграцией в коде

**result.json:**
- Генерируется `ocr_result_merger.py` через сложный merge annotation.json + ocr_html
- Fuzzy matching block ID в HTML сегментах
- Используется как source of truth для downstream (export, display) — конкурирует с annotations.data
- Нет transactional consistency с БД

Нормализованные таблицы `blocks` + `ocr_results` в Postgres устраняют оба эти антипаттерна.

### 5. Почему crop during OCR должен жить локально на backend

В legacy `task_upload.py` загружает кропы в R2 во время OCR обработки:
- Каждый strip crop = HTTP PUT к R2 (network overhead)
- Промежуточные strips/images накапливаются в R2 (storage cost)
- OCR зависит от R2 availability (single point of failure)
- Cleanup сложный — нужно удалять промежуточные файлы после завершения

Crop-ы нужны только backend серверу для отправки в LLM API. Они живут в `/tmp/ocr_{run_id}/`, используются для OCR запроса, и удаляются. Никакого network round-trip.

### 6. Почему R2 хранит только original PDF и финальный crop

**Original PDF:**
- Нужен для повторного crop при rerun, для отображения в viewer, для export
- Один файл на документ, загружается один раз

**Финальный crop (image/stamp блоков):**
- Нужен для отображения в UI (пользователь видит что распознала модель)
- Загружается после успешного OCR (не во время)
- Только для image/stamp блоков (text блоки не нуждаются в визуальном crop)

**Что НЕ хранится в R2:**
- Промежуточные strip кропы (удалены из архитектуры)
- annotation.json (state в Postgres)
- result.json (state в Postgres)
- ocr_result.html (генерируется on-demand из Postgres)
- document.md (генерируется on-demand из Postgres)

### 7. Почему нужен трёхсерверный deploy

| Сервер | Роль | Ресурсы | Причина изоляции |
|--------|------|---------|-----------------|
| Frontend (Next.js) | UI, SSR/SSG | CPU, RAM | Обновляется независимо, может быть на Vercel |
| Backend (FastAPI) | API, OCR pipeline, crop, export | CPU, RAM, disk (/tmp) | Хранит все секреты, проксирует внешние сервисы |
| LM Studio | Локальная LLM | GPU, VRAM | Ресурсоёмкий, требует GPU, может перезагружаться без влияния на web |

Ключевые аргументы:
- **Независимый deploy**: обновление frontend не требует restart backend, перезагрузка LM Studio не роняет web
- **Секреты изолированы**: frontend не имеет API ключей, LM Studio не имеет DB credentials
- **Масштабирование**: backend и LM Studio на разных машинах (CPU vs GPU)
- **Нет Celery/Redis**: упрощение инфраструктуры, async native

### 8. Как будет устроена админка

5 панелей в Next.js (`/admin/*`), доступных только admin-пользователям:

| Панель | Источник данных | Функциональность |
|--------|----------------|-----------------|
| Health Dashboard | `GET /api/admin/health` — ping каждого сервиса | Статус Backend, LM Studio, R2, Supabase, OpenRouter. CircuitBreaker state |
| Sources Availability | `GET /api/admin/sources` | Текущий статус OCR бэкендов (available/circuit_open/unknown). Latency |
| Recognition Runs | `GET /api/admin/runs` + SSE | Список OCR runs. Progress, block counts, engine, duration. Cancel |
| Block Incidents | `GET /api/admin/incidents` | Блоки с quality_score='suspicious'/'error'. Группировка по документу. Re-run |
| Events Log | `GET /api/admin/events?type=&severity=&from=&to=` | Фильтруемая таблица events. Expandable payload JSON |

Backend пишет events в таблицу `events`:
- `ocr_block_started`, `ocr_block_completed`, `ocr_block_failed`
- `ocr_run_started`, `ocr_run_completed`
- `source_available`, `source_unavailable`
- `circuit_opened`, `circuit_closed`
- `manual_edit_saved`, `export_generated`

Retention policy: `DELETE FROM events WHERE created_at < now() - interval '30 days'`.

### 9. Какие legacy-файлы переносим почти как есть

| Файл | Что берём | Адаптация |
|------|----------|-----------|
| `pdf_streaming_core.py` | `StreamingPDFProcessor`, `crop_block_image()`, `crop_block_to_pdf()`, effective zoom | Синхронный → async context, убрать strip-related функции (`merge_crops_vertically`, `create_block_separator`) |
| `openrouter.py` | `OpenRouterBackend.recognize()`, media encoding, retry session, model list caching | Timeout tuning, async HTTP (httpx вместо requests) |
| `chandra.py` | `ChandraBackend.recognize()`, model discovery, preload, time budget detection | Thread → asyncio, убрать ngrok-specific |
| `circuit_breaker.py` | CircuitBreaker state machine (CLOSED/OPEN/HALF_OPEN), global registry | `threading.Lock` → `asyncio.Lock` |
| `block_verification.py` | Логика обнаружения missing/suspicious blocks, retry с fallback | Читает из Postgres вместо result.json, async |
| `text_ocr_quality.py` | `classify_text_output()`, `filter_mixed_text_output()`, suspicious detection | Без изменений |
| `backend_factory.py` | `JobBackends` dataclass, factory pattern, fallback chain | Убрать strip backend, адаптировать конфиг |
| `html_generator.py` | Парсинг OCR JSON, форматирование IMAGE/stamp, HTML sanitization | Читает из SQL query вместо in-memory |
| `md/generator.py` | Markdown generation, stamp header, page grouping | Читает из SQL query вместо result.json |
| `logging_config.py` | JSON formatter, extra fields registry, library suppression | Без изменений |
| `block.py` | Координатная система (px + norm), конвертация, armor ID генерация | Только утилиты, не сам dataclass |
| `worker_prompts.py` | `fill_image_prompt_variables()` — variable substitution | Источник промптов → Postgres, не config.yaml |

### 10. Какие legacy-файлы использовать только как anti-reference

| Файл | Почему anti-reference | Что делать вместо |
|------|----------------------|-------------------|
| `pass2_strips.py` | Batch strip OCR — хрупкий fuzzy matching, не позволяет per-block retry | Per-block OCR: один crop → один API call → один результат |
| `worker_prompts.py::build_strip_prompt` | Batch prompt с BLOCK-маркерами для нескольких блоков | Один промпт на блок из таблицы `prompts` |
| `storage_settings.py` | Prompt lookup из config.yaml | Lookup из таблицы `prompts` в Postgres |
| `config.yaml` | Prompt texts hardcoded в файле | SQL seed миграция для начальных промптов |
| `task_upload.py` | Промежуточные crop uploads в R2 во время OCR | Кропы в `/tmp`, только финальный crop в R2 |
| `ocr_result_merger.py` | Merge annotation.json + ocr_html → result.json как primary architecture | Нет merge — данные нормализованы в `blocks` + `ocr_results` |
| `task_results.py` | `result.json` как source of truth для downstream | Source of truth = Postgres, export генерируется on-demand |
| `block.py` (table compat) | `if raw_type == "table": block_type = TEXT` — legacy migration code | Нет table в системе вообще |
| `prod.sql` (частично) | `image_categories` (промпты в category), `table_model` (мёртвый код), `jobs` как финальная модель | Новая schema: `prompts`, `blocks`, `ocr_results`, `ocr_runs`, `events` |
| Desktop GUI | Qt/PySide6 виджеты, QGraphicsView, мixin composition | Next.js + Canvas/fabric.js, React components |
