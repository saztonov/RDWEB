# Операционное руководство OCR Web MVP

> Версия: 1.0
> Дата: 2026-04-05
> Стек: FastAPI + Celery/Redis + React 18 + Supabase + Cloudflare R2 + LM Studio

---

## Содержание

1. [Health Check Endpoints](#1-health-check-endpoints)
2. [Admin Panel](#2-admin-panel)
3. [Мониторинг OCR Sources](#3-мониторинг-ocr-sources)
4. [Celery Worker Management](#4-celery-worker-management)
5. [R2 Storage Management](#5-r2-storage-management)
6. [Log Structure](#6-log-structure)
7. [Retention Policies](#7-retention-policies)
8. [Operational Runbooks](#8-operational-runbooks)

---

## 1. Health Check Endpoints

Система предоставляет четыре уровня health-проверок. Все endpoints не требуют авторизации, кроме `/api/admin/health`.

### GET /health -- Liveness

Самая простая проверка: сервер запущен и принимает HTTP-запросы. Всегда возвращает `200 OK`.

```
HTTP/1.1 200 OK
Content-Type: application/json

{"status": "alive"}
```

Применение: load balancer liveness probe, Docker `HEALTHCHECK`, Kubernetes `livenessProbe`.

### GET /health/ready -- Readiness

Проверяет готовность сервиса к обработке запросов. Выполняет три подпроверки:

| Проверка | Описание | Критичность |
|----------|----------|-------------|
| Redis ping | `PING` команда к Redis | Критична -- без Redis Celery не работает |
| Supabase SELECT | `SELECT 1` через service_role key | Критична -- без БД API бесполезен |
| Config validation | Наличие обязательных переменных окружения | Критична -- запуск без конфигурации невозможен |

Ответ при успешной readiness:

```json
{
  "status": "ready",
  "checks": {
    "redis": {"ok": true, "latency_ms": 2},
    "supabase": {"ok": true, "latency_ms": 45},
    "config": {"ok": true}
  }
}
```

Ответ при сбое (HTTP 503):

```json
{
  "status": "not_ready",
  "checks": {
    "redis": {"ok": false, "error": "Connection refused"},
    "supabase": {"ok": true, "latency_ms": 45},
    "config": {"ok": true}
  }
}
```

Применение: Kubernetes `readinessProbe`, load balancer health check, мониторинг.

### GET /queue -- Размер очереди Celery

Возвращает текущий размер очереди задач и флаг `can_accept`.

```json
{
  "queue_size": 12,
  "can_accept": true,
  "max_queue_size": 100
}
```

Логика `can_accept`:
- `true` -- `queue_size < 100`
- `false` -- `queue_size >= 100`; API должен возвращать HTTP 429 на новые OCR-запросы

Применение: UI показывает предупреждение при `can_accept: false`, backpressure.

### GET /api/admin/health -- Сводный dashboard

Требует авторизации: `app_metadata.is_admin = true`.

Агрегирует данные из всех остальных endpoints в единую картину:

```json
{
  "services": {
    "backend_api": {"status": "healthy", "latency_ms": 12},
    "supabase": {"status": "healthy", "latency_ms": 45},
    "redis": {"status": "healthy", "latency_ms": 2},
    "r2": {"status": "healthy", "latency_ms": 89},
    "lmstudio": {"status": "degraded", "latency_ms": 230},
    "openrouter": {"status": "healthy", "latency_ms": 150}
  },
  "queue": {
    "size": 12,
    "can_accept": true
  },
  "workers": [
    {
      "worker_name": "worker-1",
      "host": "backend-srv",
      "pid": 1234,
      "memory_mb": 512.3,
      "active_tasks": 2,
      "last_seen_at": "2026-04-05T12:00:05Z"
    }
  ]
}
```

Статусы сервисов: `healthy`, `degraded`, `unavailable`, `unknown`.

---

## 2. Admin Panel

Admin panel -- веб-интерфейс для оператора, встроенный в React SPA. Доступен по адресу `/admin/*`.

Подробное описание всех страниц и функциональности: [admin-panel.md](admin-panel.md).

Ключевые возможности:
- Real-time обновления через SSE
- Health dashboard сервисов
- Управление OCR sources
- Мониторинг recognition runs
- Block incidents (failed/timeout)
- Управление prompt templates
- System events log

Доступ: только пользователи с `app_metadata.is_admin = true` в Supabase Auth.

---

## 3. Мониторинг OCR Sources

### Таблицы

**ocr_sources** -- реестр OCR-провайдеров:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `id` | uuid | Primary key |
| `source_type` | enum | `openrouter`, `lmstudio` |
| `name` | text | Человекочитаемое имя |
| `base_url` | text | Base URL провайдера |
| `deployment_mode` | enum | `managed_api`, `docker`, `remote_ngrok`, `private_url` |
| `is_enabled` | boolean | Включён ли source |
| `health_status` | text | `healthy` / `degraded` / `unavailable` / `unknown` |
| `last_health_at` | timestamptz | Время последней проверки |
| `concurrency_limit` | integer | Максимум параллельных запросов |
| `timeout_sec` | integer | Таймаут одного запроса |
| `credentials_json` | jsonb | Секреты (api_key, auth_user, auth_pass) -- не отдаются на frontend |

**service_health_checks** -- снапшоты проверок:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `service_name` | text | Имя сервиса (redis, supabase, r2, lmstudio, openrouter) |
| `status` | text | `healthy` / `degraded` / `unavailable` |
| `response_time_ms` | integer | Время ответа |
| `details_json` | jsonb | Дополнительные данные (error message, circuit state) |
| `checked_at` | timestamptz | Время проверки |

**ocr_source_models_cache** -- кэш доступных моделей:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `source_id` | uuid | FK на ocr_sources |
| `model_id` | text | ID модели у провайдера |
| `model_name` | text | Человекочитаемое имя |
| `context_length` | integer | Длина контекста |
| `supports_vision` | boolean | Поддержка vision API |
| `fetched_at` | timestamptz | Время последней синхронизации |

### Celery Beat: автоматическая проверка

Task `ocr.probe_source_health` выполняется каждые 60 секунд:

1. Для каждого `ocr_sources WHERE is_enabled = true`:
   - Отправляет probe-запрос (GET /v1/models для LM Studio, GET /api/v1/models для OpenRouter)
   - Измеряет latency
   - Определяет статус (healthy / degraded / unavailable)
2. Обновляет `ocr_sources.health_status` и `last_health_at`
3. Вставляет запись в `service_health_checks`
4. При смене статуса создаёт `system_events` (source_available / source_unavailable)

### API endpoints

```
GET  /api/admin/ocr/sources
```

Возвращает список всех OCR sources с текущим health_status, latency, моделями.
Поле `credentials_json` исключается из ответа.

```
POST /api/admin/ocr/sources/{id}/healthcheck
```

Ручной запуск проверки здоровья конкретного source. Возвращает результат немедленно.

---

## 4. Celery Worker Management

### Запуск worker

```bash
celery -A app.celery_app worker \
    --loglevel=info \
    --concurrency=N \
    --max-tasks-per-child=50
```

Параметр `--max-tasks-per-child=50` перезапускает worker-процесс после каждых 50 задач для предотвращения memory leaks (PyMuPDF, Pillow).

### Docker Compose конфигурация

Файл: `infra/backend/docker-compose.yml`

Ресурсы worker-контейнера:

| Параметр | Значение |
|----------|----------|
| CPU limit | 4 |
| Memory limit | 6 GB |
| MAX_TASKS_PER_CHILD | 50 |
| CELERYD_CONCURRENCY | определяется при запуске |

### Heartbeat

Таблица `worker_heartbeats` -- пульс каждого worker:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `worker_name` | text | Уникальное имя worker (UNIQUE) |
| `queue_name` | text | Имя очереди (default, ocr, etc.) |
| `host` | text | Hostname машины |
| `pid` | integer | PID worker-процесса |
| `memory_mb` | real | Текущее потребление памяти |
| `active_tasks` | integer | Количество выполняемых задач |
| `last_seen_at` | timestamptz | Время последнего heartbeat |

Worker считается unavailable, если `last_seen_at` старше 90 секунд.

### Celery Beat Schedule

| Task | Расписание | Описание |
|------|-----------|----------|
| `ocr.probe_source_health` | Каждые 60 секунд | Проверка здоровья OCR sources |
| `ocr.cleanup_retention` | Ежедневно, 03:00 | Очистка устаревших записей (см. Retention Policies) |
| `ocr.sync_models` | Каждые 30 минут | Синхронизация кэша моделей из OCR sources |
| `ocr.worker_heartbeat` | Каждые 30 секунд | Обновление worker_heartbeats |

---

## 5. R2 Storage Management

### Что хранится в R2

| Тип файла | R2 key pattern | Когда загружается |
|-----------|---------------|-------------------|
| Original PDF | `documents/{workspace_id}/{document_id}.pdf` | При upload документа (один раз) |
| Финальный crop блока (image/stamp) | `crops/{document_id}/{block_id}.pdf` | После успешного OCR блока |

### Что НЕ хранится в R2

| Тип данных | Причина |
|------------|---------|
| Промежуточные кропы | Per-block OCR -- crop создаётся в /tmp и удаляется после обработки |
| Annotations | State хранится в Postgres (таблица blocks) |
| result.json | State хранится в Postgres (таблица recognition_attempts) |
| Text-блоков crop | Текст сохранён в Postgres, визуальный crop не нужен |

Подробное обоснование: [ADR-0005](adr/0005-local-crop-runtime-and-final-r2-upload.md).

### Crop lifecycle

```
1. Download PDF из R2 (один раз, кэшируется в /tmp)
2. Для каждого блока:
   a. StreamingPDFProcessor.crop_block_image(block)
      -> PIL Image в /tmp/ocr_{run_id}/{block_id}.png
   b. OCR backend получает crop как bytes/base64
   c. Если success И block_kind IN ('image', 'stamp'):
      -> Upload crop в R2
      -> UPDATE blocks SET current_crop_key = ...
   d. Удаление локального файла
3. rm -rf /tmp/ocr_{run_id}/
```

Состояния `crop_upload_state`:

| Состояние | Описание |
|-----------|----------|
| `none` | Crop ещё не создавался |
| `uploading` | Upload в R2 в процессе |
| `uploaded` | Crop успешно загружен в R2 |
| `failed` | Upload завершился ошибкой |

### Требования к disk space

- Temp space: ~500 MB (достаточно для 5 concurrent OCR runs)
- Cleanup cron: файлы `/tmp/ocr_*` старше 1 часа удаляются автоматически

---

## 6. Log Structure

### JSON Structured Logging

Конфигурация: `logging_config.py`

Формат production (JSON):

```json
{
  "timestamp": "2026-04-05T12:00:05.123Z",
  "level": "INFO",
  "logger": "app.ocr.pipeline",
  "message": "Block recognized",
  "event": "ocr_block_completed",
  "block_id": "abc123",
  "document_id": "doc456",
  "engine": "openrouter",
  "model_name": "google/gemini-2.0-flash-001",
  "duration_ms": 4200,
  "quality_score": "good"
}
```

Формат development: human-readable text с теми же extra-полями.

### Docker logging

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "5"
```

Каждый контейнер хранит до 5 файлов по 10 MB = максимум 50 MB логов на контейнер.

### Таблица system_events

Структурированные операционные события для admin panel:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `event_type` | text | Тип события (source_unavailable, circuit_opened, ...) |
| `severity` | text | `debug` / `info` / `warning` / `error` / `critical` |
| `source_service` | text | Источник события (backend, worker, beat) |
| `payload_json` | jsonb | Произвольные метаданные события |
| `created_at` | timestamptz | Время создания |

Типы событий:

| event_type | severity | Когда |
|------------|----------|-------|
| `ocr_run_started` | info | Начало recognition run |
| `ocr_run_completed` | info | Завершение recognition run |
| `ocr_block_failed` | error | Ошибка OCR блока |
| `source_available` | info | OCR source стал доступен |
| `source_unavailable` | error | OCR source недоступен |
| `circuit_opened` | warning | CircuitBreaker перешёл в OPEN |
| `circuit_closed` | info | CircuitBreaker перешёл в CLOSED |
| `worker_oom` | critical | Worker превысил лимит памяти |

### Таблица block_events

Audit trail по блокам:

| Колонка | Тип | Описание |
|---------|-----|----------|
| `block_id` | uuid | FK на blocks |
| `event_type` | text | created, geometry_changed, recognized, manual_edit, locked, unlocked, deleted, restored |
| `payload_json` | jsonb | Детали изменения |
| `actor_id` | uuid | Пользователь, выполнивший действие |
| `created_at` | timestamptz | Время события |

---

## 7. Retention Policies

Автоматическая очистка устаревших данных выполняется Celery task `ocr.cleanup_retention` ежедневно в 03:00.

| Таблица | Срок хранения | SQL |
|---------|---------------|-----|
| `system_events` | 30 дней | `DELETE FROM system_events WHERE created_at < now() - interval '30 days'` |
| `service_health_checks` | 7 дней | `DELETE FROM service_health_checks WHERE checked_at < now() - interval '7 days'` |
| `worker_heartbeats` | 1 день | `DELETE FROM worker_heartbeats WHERE last_seen_at < now() - interval '1 day'` |

Таблицы, которые НЕ подлежат автоматической очистке:
- `block_events` -- audit trail, хранится бессрочно
- `recognition_attempts` -- append-only история, хранится бессрочно
- `recognition_runs` -- хранится бессрочно

При необходимости ручная очистка:

```sql
-- Удалить recognition_attempts старше 90 дней (только если run завершён)
DELETE FROM recognition_attempts ra
USING recognition_runs rr
WHERE ra.run_id = rr.id
  AND rr.status IN ('completed', 'failed', 'cancelled')
  AND ra.created_at < now() - interval '90 days';
```

---

## 8. Operational Runbooks

### Runbook 1: OCR Source Down

**Симптомы:**
- `ocr_sources.health_status = 'unavailable'`
- `system_events` содержит `source_unavailable` с `severity = 'error'`
- Admin panel: карточка сервиса красная
- Recognition runs завершаются с `failed_blocks > 0`

**Диагностика:**

```sql
-- Последние проверки здоровья
SELECT service_name, status, response_time_ms, details_json, checked_at
FROM service_health_checks
WHERE service_name LIKE '%lmstudio%' OR service_name LIKE '%openrouter%'
ORDER BY checked_at DESC
LIMIT 10;

-- Связанные события
SELECT event_type, severity, payload_json, created_at
FROM system_events
WHERE event_type IN ('source_unavailable', 'circuit_opened')
ORDER BY created_at DESC
LIMIT 20;
```

**Действия:**
1. Проверить доступность source напрямую: `curl {base_url}/v1/models`
2. Для LM Studio: проверить GPU-сервер (SSH, docker ps, nvidia-smi)
3. Для OpenRouter: проверить статус на status.openrouter.ai, баланс аккаунта
4. Запустить ручной healthcheck: `POST /api/admin/ocr/sources/{id}/healthcheck`
5. При необходимости отключить source: `UPDATE ocr_sources SET is_enabled = false WHERE id = '...'`
6. Дождаться автоматического probe (1 минута) или запустить ручной

---

### Runbook 2: Worker Stuck

**Симптомы:**
- `worker_heartbeats.last_seen_at` старше 90 секунд
- Admin panel: worker показывает `active_tasks > 0`, но `last_seen_at` не обновляется
- Recognition runs зависают в статусе `running`

**Диагностика:**

```sql
-- Проверить heartbeat
SELECT worker_name, host, pid, memory_mb, active_tasks, last_seen_at,
       EXTRACT(EPOCH FROM (now() - last_seen_at)) AS seconds_since_heartbeat
FROM worker_heartbeats
ORDER BY last_seen_at DESC;

-- Зависшие runs
SELECT id, document_id, status, total_blocks, processed_blocks, started_at,
       EXTRACT(EPOCH FROM (now() - started_at)) AS running_seconds
FROM recognition_runs
WHERE status = 'running'
ORDER BY started_at ASC;
```

**Действия:**
1. Если `memory_mb` близко к лимиту (6 GB) -- worker в OOM, требуется restart
2. Проверить active_tasks: если > 0, но heartbeat не обновляется -- worker завис
3. Restart worker:
   ```bash
   docker compose -f infra/backend/docker-compose.yml restart worker
   ```
4. Зависшие runs перевести в `failed`:
   ```sql
   UPDATE recognition_runs SET status = 'failed', finished_at = now()
   WHERE status = 'running' AND started_at < now() - interval '30 minutes';
   ```
5. Проверить логи: `docker compose -f infra/backend/docker-compose.yml logs worker --tail=100`

---

### Runbook 3: Disk Full (/tmp)

**Симптомы:**
- OCR pipeline завершается с ошибкой `OSError: [Errno 28] No space left on device`
- system_events с `event_type = 'ocr_block_failed'` и error_message содержит "No space"
- Новые recognition runs немедленно fail

**Диагностика:**

```bash
# Проверить свободное место
df -h /tmp

# Найти крупные файлы OCR
du -sh /tmp/ocr_* 2>/dev/null

# Найти orphaned PDF cache
ls -la /tmp/pdf_cache_* 2>/dev/null

# Общий размер tmp
du -sh /tmp
```

**Действия:**
1. Удалить orphaned OCR crop-директории (старше 1 часа):
   ```bash
   find /tmp -name 'ocr_*' -type d -mmin +60 -exec rm -rf {} +
   ```
2. Очистить PDF cache:
   ```bash
   find /tmp -name 'pdf_cache_*' -mmin +120 -delete
   ```
3. Проверить нет ли других крупных файлов:
   ```bash
   find /tmp -size +100M -type f -ls
   ```
4. Если проблема повторяется -- увеличить disk space или уменьшить concurrency worker

---

### Runbook 4: Redis Unavailable

**Симптомы:**
- `GET /health/ready` возвращает 503 с `redis.ok = false`
- Celery worker не может получить задачи
- Новые OCR runs не запускаются (задачи не попадают в очередь)
- Admin panel: карточка Redis красная

**Диагностика:**

```bash
# Проверить статус Redis контейнера
docker compose -f infra/backend/docker-compose.yml ps redis

# Попытка подключения
docker compose -f infra/backend/docker-compose.yml exec redis redis-cli ping

# Логи Redis
docker compose -f infra/backend/docker-compose.yml logs redis --tail=50
```

**Действия:**
1. Restart Redis:
   ```bash
   docker compose -f infra/backend/docker-compose.yml restart redis
   ```
2. Проверить memory: Redis настроен с лимитом 256 MB. Если `used_memory` близко к лимиту:
   ```bash
   docker compose -f infra/backend/docker-compose.yml exec redis redis-cli info memory
   ```
3. После восстановления Redis -- проверить, что worker переподключился:
   ```bash
   docker compose -f infra/backend/docker-compose.yml logs worker --tail=20
   ```
4. Зависшие runs перевести в failed (см. Runbook 2, шаг 4)

---

### Runbook 5: Supabase Connection Lost

**Симптомы:**
- `GET /health/ready` возвращает 503 с `supabase.ok = false`
- HTTP 500 на любых API-запросах, требующих БД
- Логи содержат `connection refused` или `timeout` для Postgres

**Диагностика:**

```bash
# Проверить доступность Supabase (для managed)
curl -s https://<project-ref>.supabase.co/rest/v1/ \
  -H "apikey: <anon_key>" \
  -H "Authorization: Bearer <anon_key>"

# Для local Supabase
supabase status
docker compose -f supabase/docker-compose.yml ps
```

**Действия:**
1. Для managed Supabase:
   - Проверить статус на status.supabase.com
   - Проверить не истёк ли проект (free tier: пауза после 7 дней неактивности)
   - Проверить credentials в `.env`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
2. Для local Supabase:
   ```bash
   supabase stop && supabase start
   ```
3. Проверить, что после восстановления readiness pass:
   ```bash
   curl http://localhost:8000/health/ready
   ```
4. Если credentials изменились -- обновить `.env` и перезапустить backend:
   ```bash
   docker compose -f infra/backend/docker-compose.yml restart api worker
   ```

---

### Runbook 6: Массовые Quality Incidents

**Симптомы:**
- Резкий рост блоков со статусом `failed` или `manual_review`
- Admin panel: страница Incidents показывает много записей за короткий период
- Пользователи сообщают о некорректных результатах OCR

**Диагностика:**

```sql
-- Корреляция с source availability
SELECT
    se.event_type,
    se.payload_json,
    se.created_at
FROM system_events se
WHERE se.event_type IN ('source_unavailable', 'circuit_opened', 'source_available')
  AND se.created_at > now() - interval '1 hour'
ORDER BY se.created_at DESC;

-- Failed attempts по source
SELECT
    ra.source_id,
    os.name AS source_name,
    ra.status,
    ra.error_code,
    COUNT(*) AS attempt_count
FROM recognition_attempts ra
JOIN ocr_sources os ON os.id = ra.source_id
WHERE ra.created_at > now() - interval '1 hour'
  AND ra.status IN ('failed', 'timeout')
GROUP BY ra.source_id, os.name, ra.status, ra.error_code
ORDER BY attempt_count DESC;

-- Runs с высоким процентом failures
SELECT
    rr.id, rr.document_id, rr.run_mode,
    rr.total_blocks, rr.failed_blocks,
    ROUND(rr.failed_blocks::numeric / NULLIF(rr.total_blocks, 0) * 100, 1) AS fail_pct,
    rr.started_at
FROM recognition_runs rr
WHERE rr.created_at > now() - interval '1 hour'
  AND rr.failed_blocks > 0
ORDER BY fail_pct DESC;
```

**Действия:**
1. Определить, связана ли проблема с конкретным source:
   - Если все failures на одном source -- см. Runbook 1
   - Если проблема на всех sources -- проверить network
2. Для affected blocks выполнить block_rerun:
   ```
   POST /api/blocks/{block_id}/rerun
   ```
3. Если причина -- некорректный prompt template:
   - Проверить последние изменения в `prompt_templates`
   - Откатить к предыдущей версии (create new version + activate)
4. Если проблема в модели (деградация качества):
   - Изменить `profile_routes.primary_model_name` на альтернативную модель
   - Или переключить на fallback source
