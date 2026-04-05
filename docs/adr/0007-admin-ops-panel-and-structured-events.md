# ADR-0007: Admin/ops панель и structured events

> Дата: 2026-04-05
> Статус: Принят

## Контекст

### Legacy monitoring

Legacy OCR сервер имеет минимальный monitoring:

1. **`/health` endpoint** — проверка alive (HTTP 200)
2. **`logging_config.py`** — structured JSON logging с extra fields:
   - Task context: `job_id`, `task_id`, `client_id`, `document_name`
   - Performance: `duration_ms`, `memory_mb`, `concurrency`
   - OCR context: `engine`, `model_name`, `phase`, `strip_count`
   - Storage: `r2_prefix`, `file_size`
3. **Celery signals** — `task_prerun`, `task_postrun`, `task_failure` для lifecycle tracking
4. **Нет admin UI** — мониторинг только через логи и CLI

### Проблемы без admin панели

1. **LM Studio может быть offline** — circuit breaker блокирует запросы, но оператор не видит причину
2. **OpenRouter rate limit** — тихо деградирует quality, оператор узнаёт только из результатов
3. **Quality деградация** — `suspicious` результаты копятся, нет alarm
4. **Прогресс OCR** — нет visibility в real-time
5. **Incident correlation** — нельзя связать "много ошибок" с "LM Studio перезагрузился"

### Правило #12 из пролога

> На сайте должна быть admin/ops панель: health panel, sources availability, recognition runs, block incidents, logs/events

Это обязательное требование.

## Решение

### Admin панель в Next.js

Роутинг `/admin/*`, доступный только admin-пользователям (проверка роли через Supabase Auth).

#### Панель 1: Health Dashboard

```
┌─ Health ─────────────────────────────────────────────────┐
│                                                          │
│  Backend API          ✅ healthy    latency: 12ms        │
│  Supabase Postgres    ✅ healthy    latency: 45ms        │
│  Cloudflare R2        ✅ healthy    latency: 89ms        │
│  LM Studio (Chandra)  🟡 half_open latency: 230ms       │
│  OpenRouter           ✅ healthy    latency: 150ms       │
│                                                          │
│  Последнее обновление: 12:00:05                          │
└──────────────────────────────────────────────────────────┘
```

Backend endpoint: `GET /api/admin/health`
- Ping каждого сервиса: Supabase (`SELECT 1`), R2 (`HEAD bucket`), LM Studio (`GET /v1/models`), OpenRouter (`GET /api/v1/models`)
- CircuitBreaker state для LM Studio и OpenRouter
- Latency последних запросов

#### Панель 2: Sources Availability

```
┌─ Sources ────────────────────────────────────────────────┐
│                                                          │
│  Source          Status       Circuit    Avg Latency      │
│  ─────────────────────────────────────────────────────── │
│  Chandra         ✅ available  CLOSED     4.2s            │
│  OpenRouter      ✅ available  CLOSED     2.1s            │
│                                                          │
│  Circuit Breaker Config:                                 │
│  failure_threshold: 3 | recovery_timeout: 60s            │
└──────────────────────────────────────────────────────────┘
```

Backend endpoint: `GET /api/admin/sources`
- Текущий статус каждого OCR backend
- CircuitBreaker state (CLOSED/OPEN/HALF_OPEN) с timestamps
- Средняя latency за последние 10 запросов

#### Панель 3: Recognition Runs

```
┌─ Recognition Runs ──────────────────────────────────────┐
│                                                          │
│  Фильтр: [Все ▼] [Сегодня ▼]                           │
│                                                          │
│  ID     Document        Engine    Progress   Status      │
│  ─────────────────────────────────────────────────────── │
│  abc1   plan_1.pdf      chandra   ▓▓▓▓▓░ 85%  🔄        │
│  abc2   section_ar.pdf  chandra   ▓▓▓▓▓▓ 100% ✅        │
│  abc3   schema_2.pdf    openrout  ▓▓░░░░ 30%  ❌ error   │
│                                                          │
│  [Детали] [Cancel] [Re-run]                             │
└──────────────────────────────────────────────────────────┘
```

Backend endpoint: `GET /api/admin/runs`
- Список текущих и завершённых OCR runs
- Progress bar (processed_blocks / total_blocks)
- Engine, duration, error_message
- Actions: cancel (running), re-run (error/done)

#### Панель 4: Block Incidents

```
┌─ Block Incidents ───────────────────────────────────────┐
│                                                          │
│  Фильтр: [suspicious ▼] [Все документы ▼]              │
│                                                          │
│  Block         Document        Quality     Engine        │
│  ─────────────────────────────────────────────────────── │
│  ABCD-EFGH     plan_1.pdf      suspicious  chandra       │
│  IJKL-MNOP     plan_1.pdf      error       openrouter    │
│  QRST-UVWX     section.pdf     suspicious  chandra       │
│                                                          │
│  Всего: 3 incidents | 2 suspicious | 1 error            │
│  [Re-run selected] [View block]                         │
└──────────────────────────────────────────────────────────┘
```

Backend endpoint: `GET /api/admin/incidents`
- Блоки с `quality_score IN ('suspicious', 'error')`
- Группировка по документу
- Actions: re-run (повторное OCR), view (открыть в viewer)

#### Панель 5: Events Log

```
┌─ Events ────────────────────────────────────────────────┐
│                                                          │
│  Фильтр: [Все типы ▼] [Все ▼] [Последние 24h ▼]       │
│                                                          │
│  Time      Type                Severity  Engine  Detail  │
│  ─────────────────────────────────────────────────────── │
│  12:00:05  ocr_block_completed info      chandra [▶]     │
│  12:00:03  ocr_block_started   info      chandra [▶]     │
│  11:59:50  circuit_opened      warning   chandra [▶]     │
│  11:59:45  ocr_block_failed    error     chandra [▶]     │
│                                                          │
│  [▶] = expandable payload JSON                           │
└──────────────────────────────────────────────────────────┘
```

Backend endpoint: `GET /api/admin/events?type=&severity=&from=&to=`
- Фильтруемая таблица events
- Expandable payload JSON для каждого event
- Пагинация

### Structured Events (таблица events)

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    severity TEXT DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'error')),
    document_id UUID,
    block_id UUID,
    run_id UUID,
    engine TEXT,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### Event types

| Event Type | Severity | Когда | Payload |
|------------|----------|-------|---------|
| `ocr_run_started` | info | Начало OCR run | `{total_blocks, engine, document_name}` |
| `ocr_run_completed` | info | Завершение OCR run | `{processed, successful, failed, duration_ms}` |
| `ocr_block_started` | info | Начало OCR блока | `{block_kind, engine, attempt}` |
| `ocr_block_completed` | info | Успешный OCR блока | `{block_kind, engine, quality_score, duration_ms}` |
| `ocr_block_failed` | error | Ошибка OCR блока | `{block_kind, engine, error_message, attempt}` |
| `ocr_block_retry` | warning | Retry блока (fallback) | `{block_kind, primary_engine, fallback_engine, reason}` |
| `source_available` | info | Сервис стал доступен | `{engine, latency_ms}` |
| `source_unavailable` | error | Сервис недоступен | `{engine, error_message}` |
| `circuit_opened` | warning | CircuitBreaker → OPEN | `{engine, failure_count, threshold}` |
| `circuit_closed` | info | CircuitBreaker → CLOSED | `{engine, recovery_duration_ms}` |
| `manual_edit_saved` | info | Ручное редактирование результата | `{block_kind, user_id}` |
| `export_generated` | info | Генерация export | `{format, document_name, block_count}` |
| `document_uploaded` | info | Загрузка PDF | `{document_name, page_count, file_size}` |

### EventLogger (backend модуль)

```python
class EventLogger:
    async def emit(self,
        event_type: str,
        severity: str = "info",
        document_id: str = None,
        block_id: str = None,
        run_id: str = None,
        engine: str = None,
        **payload
    ):
        await db.execute(
            "INSERT INTO events (event_type, severity, document_id, block_id, run_id, engine, payload) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            event_type, severity, document_id, block_id, run_id, engine, json.dumps(payload)
        )
```

### Retention policy

```sql
-- Cron job (ежедневно): удалять events старше 30 дней
DELETE FROM events WHERE created_at < now() - interval '30 days';
```

### Structured logging (сохраняется из legacy)

`logging_config.py` формат сохраняется для server-side logs:
- JSON mode (production): те же extra fields (`job_id`, `duration_ms`, `engine`, etc.)
- Text mode (development): human-readable
- Events table — для UI; logs — для ELK/CloudWatch

## Последствия

### Положительные
- **Full visibility**: оператор видит статус всех сервисов, прогресс OCR, инциденты
- **Быстрая диагностика**: circuit breaker state + events log = корреляция причин
- **Proactive monitoring**: suspicious блоки видны до того, как пользователь пожалуется
- **Audit trail**: events фиксируют кто, когда, что сделал
- **Structured events**: queryable в SQL, фильтруемые в UI

### Отрицательные
- **Events table растёт**: ~100 events/document × 1000 docs = 100K rows/month → retention policy обязателен
- **Extra DB writes**: каждый OCR блок = INSERT в events → mitigation: batch insert или async queue
- **Admin UI development**: 5 панелей — дополнительная работа → mitigation: Tailwind + React Query = быстрая разработка

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Внешний monitoring (Grafana + Prometheus) | Можно добавить позже, но MVP нуждается в in-app visibility |
| Только server logs без events table | Logs неудобны для UI-панели, нужна queryable таблица |
| Отложить admin panel на post-MVP | Правило #12 делает это обязательным |
| Datadog / New Relic | Cost + vendor lock-in для MVP; structured events достаточно |
