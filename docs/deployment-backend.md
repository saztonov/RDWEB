# Deployment: Backend

Руководство по запуску, настройке и деплою backend-компонентов OCR Web MVP.

---

## 1. Компоненты

Backend состоит из трёх сервисов, управляемых через Docker Compose (`infra/backend/docker-compose.yml`):

| Сервис     | Роль                                      | Runtime          |
|------------|-------------------------------------------|------------------|
| **api**    | FastAPI HTTP-сервер (uvicorn)             | Python 3.11+     |
| **worker** | Celery OCR worker для фоновой обработки   | Python 3.11+     |
| **redis**  | Message broker (Celery) + pub/sub (SSE)   | Redis Alpine      |

Все секреты (service role keys, API keys, R2 credentials) находятся только на backend-сервере. Frontend не получает доступ к ним.

---

## 2. FastAPI: запуск

### Dev-режим

```bash
cd services/api
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Или через Docker Compose с override:

```bash
cd infra/backend
docker compose -f docker-compose.yml -f docker-compose.override.yml up
```

Override (`docker-compose.override.yml`) включает:
- Hot reload с volume mount `services/api` -> `/app`
- Нет ограничений памяти
- Redis порт 6379 доступен на host

### Production

```bash
cd infra/backend
docker compose up -d
```

API доступен только на `127.0.0.1:8000` (не на `0.0.0.0`). Внешний доступ -- через nginx reverse proxy.

### Lifespan (startup/shutdown)

При запуске `app.main:app` автоматически инициализирует:

1. **Supabase client** -- service_role, обходит RLS
2. **R2Client** -- presigned URLs и файловые операции с Cloudflare R2
3. **PdfCacheManager** -- кеш PDF в temp-директории (TTL 3600 секунд)
4. **SourceRegistry** -- реестр OCR-провайдеров, загружается из таблицы `ocr_sources`

При остановке:
- Закрытие всех провайдеров в SourceRegistry
- Очистка expired PDF-кешей

---

## 3. Environment Variables

Все переменные задаются в файле `.env` в корне проекта или через `env_file` в Docker Compose.

### Supabase

| Переменная      | Описание                           | Пример                                  |
|-----------------|------------------------------------|-----------------------------------------|
| `SUPABASE_URL`  | URL Supabase-проекта               | `https://xxx.supabase.co`               |
| `SUPABASE_KEY`  | Service role key (обходит RLS)     | `eyJhbGciOi...`                         |

### Redis

| Переменная  | Описание                   | По умолчанию                |
|-------------|----------------------------|-----------------------------|
| `REDIS_URL` | Connection string Redis    | `redis://localhost:6379/0`  |

В Docker Compose переопределяется на `redis://redis:6379/0`.

### Cloudflare R2

| Переменная              | Описание                       |
|-------------------------|--------------------------------|
| `R2_ACCOUNT_ID`         | Cloudflare account ID          |
| `R2_ACCESS_KEY_ID`      | R2 access key ID               |
| `R2_SECRET_ACCESS_KEY`  | R2 secret access key           |
| `R2_BUCKET_NAME`        | Название bucket для документов |

### OCR-провайдеры

| Переменная             | Описание                                  |
|------------------------|-------------------------------------------|
| `OPENROUTER_API_KEY`   | API key для OpenRouter (cloud OCR)        |
| `OPENROUTER_BASE_URL`  | Base URL OpenRouter API                   |
| `CHANDRA_BASE_URL`     | URL LM Studio сервера                     |
| `DATALAB_API_KEY`      | API key для Datalab (если используется)   |

### API

| Переменная       | Описание                                    |
|------------------|---------------------------------------------|
| `API_SECRET_KEY` | Секретный ключ для подписи внутренних токенов |

### Celery Worker

| Переменная                  | Описание                            | По умолчанию |
|-----------------------------|-------------------------------------|-------------|
| `CELERY_BROKER_URL`         | URL Redis для Celery broker         | (из Docker) |
| `CELERY_RESULT_BACKEND`     | URL Redis для результатов Celery    | (из Docker) |
| `CELERY_CONCURRENCY`        | Количество параллельных workers     | `2`         |
| `WORKER_MAX_TASKS_PER_CHILD`| Перезапуск worker после N задач     | --          |

---

## 4. Docker Compose

Файл: `infra/backend/docker-compose.yml`

### api

```yaml
api:
  build:
    context: ../../services/api
    dockerfile: Dockerfile
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000
  ports:
    - "127.0.0.1:8000:8000"   # только localhost
  env_file:
    - ../../.env
  environment:
    - REDIS_URL=redis://redis:6379/0
  depends_on:
    - redis
  restart: always
  mem_limit: 512m
```

### worker

```yaml
worker:
  build:
    context: ../../workers/ocr
    dockerfile: Dockerfile
  command: >
    celery -A app.celery_app worker
    --loglevel=info
    --concurrency=${CELERY_CONCURRENCY:-2}
  env_file:
    - ../../.env
  environment:
    - CELERY_BROKER_URL=redis://redis:6379/0
    - CELERY_RESULT_BACKEND=redis://redis:6379/0
  depends_on:
    - redis
  restart: always
  deploy:
    resources:
      limits:
        cpus: "4.0"
        memory: 6G
```

### redis

```yaml
redis:
  image: redis:alpine
  restart: always
  volumes:
    - redis_data:/data
  mem_limit: 256m
```

### Ресурсы (сводка)

| Сервис   | CPU    | RAM     | Порт             |
|----------|--------|---------|------------------|
| api      | --     | 512 MB  | 127.0.0.1:8000   |
| worker   | 4 CPU  | 6 GB    | --               |
| redis    | --     | 256 MB  | (internal)       |

Все сервисы используют JSON-логирование с ротацией (max-size 10 MB, max-file 5).

---

## 5. Health Checks

Backend предоставляет три endpoint-а для мониторинга:

### GET /health

Liveness check. Отвечает `200 OK` если процесс запущен.

```json
{"ok": true}
```

### GET /health/ready

Readiness check. Проверяет все зависимости:

- **redis** -- ping к Redis
- **supabase** -- запрос к таблице `workspaces`
- **config** -- хотя бы один OCR-провайдер настроен (`openrouter_api_key`, `datalab_api_key` или `chandra_base_url`)

Ответ `200` если все проверки пройдены, `503` если хотя бы одна провалилась:

```json
{
  "ready": true,
  "checks": {
    "redis": true,
    "supabase": true,
    "config": true
  }
}
```

### GET /queue

Статус очереди Celery для мониторинга backpressure:

```json
{
  "can_accept": true,
  "size": 3,
  "max": 100
}
```

Если `size` приближается к `max` (100), frontend должен показать предупреждение пользователю.

---

## 6. Reverse Proxy

Backend не должен быть доступен напрямую из интернета. Используйте nginx как reverse proxy.

### Nginx конфигурация

```nginx
location /api/ {
    proxy_pass http://backend-server:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### SSE (Server-Sent Events)

Для корректной работы event-stream добавьте в блок `/api/`:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
```

Без `proxy_buffering off` nginx буферизует SSE-ответы, и клиент не получает события в реальном времени.

### HTTPS

HTTPS termination происходит на уровне reverse proxy.
Backend работает по HTTP на `127.0.0.1:8000`.

Варианты:
- **certbot** + nginx (бесплатные сертификаты Let's Encrypt)
- **Cloudflare** (Full SSL, проксирование трафика)

---

## 7. Production Checklist

- [ ] `.env` заполнен всеми обязательными переменными
- [ ] `SUPABASE_KEY` -- это service_role key (не anon key)
- [ ] Redis persistent volume настроен (`redis_data`)
- [ ] `docker compose up -d` запускается без ошибок
- [ ] `GET /health` возвращает `{"ok": true}`
- [ ] `GET /health/ready` возвращает `{"ready": true}` со всеми проверками
- [ ] API слушает на `127.0.0.1:8000` (не `0.0.0.0`)
- [ ] Nginx reverse proxy настроен с SSE-поддержкой
- [ ] HTTPS termination на proxy level
- [ ] Логирование: JSON format с ротацией
- [ ] Worker `restart: always` для автоматического восстановления
- [ ] Мониторинг: `/health/ready` + `/queue` в системе алертов
- [ ] Backup стратегия для Redis (если используется для результатов)
- [ ] R2 bucket создан и credentials проверены
- [ ] Firewall: порт 8000 закрыт для внешнего трафика
