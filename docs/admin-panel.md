# Руководство оператора: Admin Panel

> Версия: 1.0
> Дата: 2026-04-05
> Связанные документы: [operations.md](operations.md), [ADR-0007](adr/0007-admin-ops-panel-and-structured-events.md)

---

## Содержание

1. [Обзор](#1-обзор)
2. [Overview Page (/admin)](#2-overview-page-admin)
3. [Sources Management](#3-sources-management)
4. [Recognition Runs (/admin/runs)](#4-recognition-runs-adminruns)
5. [Block Incidents (/admin/incidents)](#5-block-incidents-adminincidents)
6. [Prompt Templates (/admin/prompt-templates)](#6-prompt-templates-adminprompt-templates)
7. [System Events (/admin/events)](#7-system-events-adminevents)

---

## 1. Обзор

### Доступ

Admin panel доступна только пользователям с правами глобального администратора. Признак admin хранится в Supabase Auth:

```
app_metadata.is_admin = true
```

Установка прав через Supabase Dashboard или SQL:

```sql
UPDATE auth.users
SET raw_app_meta_data = raw_app_meta_data || '{"is_admin": true}'::jsonb
WHERE email = 'operator@example.com';
```

На backend проверка выполняется через dependency `require_admin`, которая читает JWT claim `app_metadata.is_admin`.

### URL-структура

Все страницы admin panel расположены в React SPA по prefix `/admin/*`:

| URL | Страница |
|-----|----------|
| `/admin` | Overview -- сводный dashboard |
| `/admin/sources` | OCR Sources management |
| `/admin/runs` | Recognition Runs |
| `/admin/runs/{id}` | Run Detail |
| `/admin/incidents` | Block Incidents |
| `/admin/prompt-templates` | Prompt Templates |
| `/admin/prompt-templates/{id}` | Template Detail |
| `/admin/events` | System Events |

### Real-time: Server-Sent Events (SSE)

Admin panel получает обновления в реальном времени через SSE-подключение:

```
GET /api/admin/sse?token=<JWT>
```

JWT передаётся как query-параметр, поскольку EventSource API не поддерживает custom headers.

#### Каналы SSE

| Канал | Данные | Применение |
|-------|--------|------------|
| `admin:health` | Изменение health_status сервисов | Overview: обновление карточек |
| `admin:events` | Новые system_events | Events page: добавление строки |
| `admin:runs` | Прогресс recognition runs (processed_blocks, status) | Runs page: обновление прогресса |
| `admin:workers` | Worker heartbeat обновления (memory, active_tasks) | Overview: worker summary |

Формат SSE-сообщения:

```
event: admin:health
data: {"service": "lmstudio", "status": "unavailable", "latency_ms": null}

event: admin:runs
data: {"run_id": "abc-123", "processed_blocks": 15, "total_blocks": 42, "status": "running"}
```

### State Management

| Компонент | Назначение |
|-----------|------------|
| `useAdminStore` (Zustand) | Глобальное состояние admin panel: health, workers, active runs |
| `useAdminSSE` hook | Подключение к SSE, диспатч событий в store |

Zustand store обновляется при получении SSE-событий. При потере SSE-соединения hook выполняет reconnect с exponential backoff (1s, 2s, 4s, max 30s).

---

## 2. Overview Page (/admin)

Главная страница admin panel. Отображает сводную информацию о состоянии системы.

### Health карточки сервисов

Backend endpoint: `GET /api/admin/health`

Каждый сервис представлен карточкой с цветовой индикацией:

| Статус | Цвет | Описание |
|--------|------|----------|
| `healthy` | Зелёный | Сервис работает нормально |
| `degraded` | Жёлтый | Сервис работает с ограничениями (высокая latency, partial failures) |
| `unavailable` | Красный | Сервис недоступен |
| `unknown` | Серый | Статус неизвестен (проверка ещё не выполнялась) |

Список сервисов:

| Сервис | Проверка |
|--------|----------|
| Backend API | Self-ping (всегда healthy, если страница загрузилась) |
| Supabase Postgres | `SELECT 1` через service_role key |
| Redis | `PING` команда |
| Cloudflare R2 | `HEAD` на bucket |
| LM Studio | `GET /v1/models` + CircuitBreaker state |
| OpenRouter | `GET /api/v1/models` + CircuitBreaker state |

Карточки обновляются через SSE-канал `admin:health`.

### Queue Summary

Backend endpoint: `GET /queue`

| Поле | Описание |
|------|----------|
| `queue_size` | Текущее количество задач в очереди Celery |
| `can_accept` | `true` если queue_size < 100 |

При `can_accept = false` отображается предупреждение: "Очередь переполнена. Новые запуски OCR будут отклонены".

### Worker Summary

Данные из таблицы `worker_heartbeats`, обновляемые через SSE-канал `admin:workers`.

| Колонка | Описание |
|---------|----------|
| Worker Name | Имя worker-процесса |
| Host | Hostname машины |
| PID | Process ID |
| Memory | Текущее потребление (MB) |
| Active Tasks | Количество выполняемых задач |
| Last Seen | Время последнего heartbeat |

Worker подсвечивается красным, если `last_seen_at` старше 90 секунд.

---

## 3. Sources Management

### Таблица OCR Sources

Backend endpoint: `GET /api/admin/ocr/sources`

Отображает все зарегистрированные OCR sources из таблицы `ocr_sources`.

| Колонка | Описание |
|---------|----------|
| Name | Человекочитаемое имя source |
| Type | `openrouter` / `lmstudio` |
| Deployment Mode | `managed_api` / `docker` / `remote_ngrok` / `private_url` |
| Health | Badge с текущим статусом (healthy / degraded / unavailable / unknown) |
| Latency | Средняя latency последних проверок (ms) |
| Enabled | Toggle вкл/выкл |
| Concurrency | Лимит параллельных запросов |
| Timeout | Таймаут запроса (sec) |

Поле `credentials_json` не отображается и не отдаётся API.

### Models Cache

Backend endpoint: `GET /api/admin/ocr/sources/{id}` (включает models)

Для каждого source отображается список кэшированных моделей из таблицы `ocr_source_models_cache`:

| Колонка | Описание |
|---------|----------|
| Model ID | Идентификатор модели у провайдера (например, `google/gemini-2.0-flash-001`) |
| Model Name | Человекочитаемое имя |
| Context Length | Максимальная длина контекста (tokens) |
| Supports Vision | Поддерживает ли vision API (необходимо для OCR) |
| Fetched At | Время последней синхронизации |

Кэш обновляется автоматически Celery task `ocr.sync_models` каждые 30 минут.

### Ручной Healthcheck

Backend endpoint: `POST /api/admin/ocr/sources/{id}/healthcheck`

Кнопка "Check Now" рядом с каждым source. Выполняет probe немедленно и возвращает результат:

```json
{
  "source_id": "...",
  "status": "healthy",
  "latency_ms": 142,
  "models_count": 15,
  "checked_at": "2026-04-05T12:00:05Z"
}
```

---

## 4. Recognition Runs (/admin/runs)

Backend endpoint: `GET /api/admin/runs`

### Фильтры

| Фильтр | Тип | Описание |
|--------|-----|----------|
| Status | Select | `pending` / `running` / `completed` / `failed` / `cancelled` / все |
| Document ID | Text input | UUID документа (точный поиск) |
| Date Range | Date picker | Период created_at (from -- to) |

### Колонки таблицы

| Колонка | Описание |
|---------|----------|
| Document Title | Название документа (JOIN с documents) |
| Run Mode | `full` / `smart` / `block_rerun` |
| Status | Текущий статус run с цветовой индикацией |
| Total Blocks | Общее количество блоков в run |
| Dirty Blocks | Количество блоков, требовавших обработки |
| Processed | Количество обработанных блоков |
| Recognized | Количество успешно распознанных |
| Failed | Количество с ошибками |
| Started At | Время начала |
| Duration | Продолжительность (или elapsed, если running) |

Для runs в статусе `running` отображается progress bar: `processed_blocks / total_blocks`.

Обновление в реальном времени через SSE-канал `admin:runs`.

### Run Detail (/admin/runs/{id})

Backend endpoint: `GET /api/admin/runs/{id}`

Детальная информация о конкретном run:

**Header:**
- Document title, run_mode, status, initiated_by
- Временные метки: created_at, started_at, finished_at
- Счётчики: total / dirty / processed / recognized / failed / manual_review

**Список блоков run:**

Backend endpoint: `GET /api/admin/runs/{id}/blocks`

Для каждого блока отображается:

| Колонка | Описание |
|---------|----------|
| Block ID | UUID блока |
| Page | Номер страницы |
| Kind | `text` / `stamp` / `image` |
| Status | Статус последнего attempt (`success` / `failed` / `timeout` / `skipped`) |
| Source | OCR source, использованный для attempt |
| Model | Название модели |
| Duration | Время обработки (ms) |
| Error | error_code + error_message (если failed) |

**Attempts блока:**

Нажатие на блок раскрывает историю всех recognition_attempts:

| Колонка | Описание |
|---------|----------|
| Attempt No | Номер попытки |
| Fallback No | Номер fallback (0 = primary source) |
| Source / Model | Использованный source и модель |
| Status | `pending` / `running` / `success` / `failed` / `timeout` / `skipped` |
| Quality Flags | JSON с флагами качества |
| Selected | Была ли эта попытка выбрана как текущий результат |
| Duration | Время выполнения |

---

## 5. Block Incidents (/admin/incidents)

Backend endpoint: `GET /api/admin/incidents`

Страница отображает recognition_attempts со статусом `failed` или `timeout` -- потенциальные проблемы, требующие внимания оператора.

### Фильтры

| Фильтр | Тип | Описание |
|--------|-----|----------|
| Error Code | Select | Код ошибки (timeout, rate_limit, invalid_response, ...) |
| Source ID | Select | OCR source |
| Document ID | Text input | UUID документа |
| Date Range | Date picker | Период created_at |

### Колонки

| Колонка | Описание |
|---------|----------|
| Block ID | UUID блока |
| Document | Название документа |
| Page | Номер страницы |
| Kind | Тип блока |
| Error Code | Код ошибки |
| Error Message | Текст ошибки |
| Source | OCR source |
| Model | Модель |
| Created At | Время attempt |

### Действия

| Действие | Описание |
|----------|----------|
| Re-run | Перезапуск OCR для блока (`POST /api/blocks/{block_id}/rerun`) |
| View Block | Переход к документу с фокусом на блоке |
| View Run | Переход к странице Run Detail |

Массовые операции: выделить несколько incidents -> "Re-run Selected" запускает block_rerun для всех выбранных блоков.

---

## 6. Prompt Templates (/admin/prompt-templates)

Backend endpoint: `GET /api/admin/prompt-templates`

Управление промптами для OCR-распознавания. Промпты -- единственный источник инструкций для LLM; никаких prompt text в config-файлах или env-переменных.

### Список templates

| Колонка | Описание |
|---------|----------|
| Template Key | Уникальный ключ шаблона (например, `text_openrouter`) |
| Version | Номер версии |
| Is Active | Активен ли шаблон (зелёный/серый badge) |
| Block Kind | `text` / `stamp` / `image` |
| Source Type | `openrouter` / `lmstudio` |
| Profile | Связанный document profile |
| Parser | Стратегия парсинга результата |
| Updated At | Время последнего изменения |

Сортировка по умолчанию: template_key ASC, version DESC.

### Template Detail (/admin/prompt-templates/{id})

Backend endpoint: `GET /api/admin/prompt-templates/{id}`

**Метаданные (readonly):**
- template_key, version, is_active
- block_kind, source_type, model_pattern
- document_profile_id
- parser_strategy
- notes
- created_at, updated_at, created_by, updated_by

**Редактируемые поля:**

| Поле | Описание |
|------|----------|
| `system_template` | Системный промпт -- инструкции для LLM (role, context) |
| `user_template` | Пользовательский промпт -- конкретная задача |
| `output_schema_json` | JSON Schema для structured output (stamp, image) |
| `parser_strategy` | Стратегия парсинга: `plain_text`, `json_schema`, `markdown`, `html`, `regex` |
| `notes` | Заметки оператора |

Промпты поддерживают переменные подстановки:
- `{DOC_NAME}` -- название документа
- `{PAGE_NUM}` -- номер страницы
- `{BLOCK_KIND}` -- тип блока
- `{HINT}` -- подсказка оператора (если задана)

### Операции

| Операция | Описание |
|----------|----------|
| Create | Создать новый template с нуля |
| Clone | Скопировать существующий template как новый template_key |
| New Version | Создать новую версию текущего template (version + 1). Предыдущая версия автоматически деактивируется |
| Activate | Сделать эту версию активной (`is_active = true`). Остальные версии того же template_key деактивируются |
| Edit | Редактирование system_template, user_template, notes, output_schema_json |

**Версионирование:**

Constraint `UNIQUE (template_key, version)` гарантирует уникальность. При создании новой версии:

1. Новая запись с `version = max(version) + 1` для данного `template_key`
2. Все остальные версии того же key: `is_active = false`
3. Новая версия: `is_active = true`

Откат к предыдущей версии: выбрать нужную версию -> нажать "Activate".

---

## 7. System Events (/admin/events)

Backend endpoint: `GET /api/admin/events`

Таблица system_events -- структурированные операционные события системы. Обновляется в реальном времени через SSE-канал `admin:events`.

### Фильтры

| Фильтр | Тип | Описание |
|--------|-----|----------|
| Severity | Select | `debug` / `info` / `warning` / `error` / `critical` / все |
| Source Service | Select | `backend` / `worker` / `beat` / все |
| Event Type | Select | Тип события (source_unavailable, circuit_opened, ...) |
| Date Range | Date picker | Период created_at |

### Колонки

| Колонка | Описание |
|---------|----------|
| Time | Время события (created_at) |
| Severity | Badge с цветовой индикацией |
| Event Type | Тип события |
| Source Service | Источник |
| Summary | Краткое описание (генерируется из payload_json) |
| Expand | Кнопка раскрытия полного payload |

### Severity Levels

| Уровень | Цвет | Применение |
|---------|------|------------|
| `debug` | Серый | Отладочная информация (обычно отфильтрована) |
| `info` | Синий | Штатные операции: run started/completed, source available |
| `warning` | Жёлтый | Предупреждения: circuit opened, retry, degraded performance |
| `error` | Красный | Ошибки: source unavailable, block failed, connection lost |
| `critical` | Тёмно-красный | Критические: worker OOM, data corruption, security events |

### Expandable Payload

Нажатие на строку или кнопку expand раскрывает полный `payload_json` в отформатированном виде:

```json
{
  "engine": "lmstudio",
  "error_message": "Connection refused: http://localhost:1234/v1/chat/completions",
  "failure_count": 3,
  "threshold": 3,
  "last_success_at": "2026-04-05T11:55:00Z"
}
```

Payload JSON копируется в буфер обмена по нажатию кнопки "Copy".

### Retention

События хранятся 30 дней. Автоматическая очистка выполняется Celery task `ocr.cleanup_retention` ежедневно. Подробнее: [operations.md, раздел Retention Policies](operations.md#7-retention-policies).
