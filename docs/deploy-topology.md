# Продакшен-топология

## Три независимых сервера

### 1. Web Server

Раздаёт React SPA через nginx. **Не содержит секретов.**

- **Окружение:**
  - `BACKEND_URL` — адрес backend-сервера
  - `VITE_SUPABASE_URL` — публичный URL Supabase
  - `VITE_SUPABASE_ANON_KEY` — публичный anon key Supabase
- **Деплой:** nginx, CDN, Vercel или любой static host
- **Docker:** `infra/web/docker-compose.yml`
- **Память:** ~128 MB

### 2. Backend Server

FastAPI + Celery worker + Redis. **Все секреты только здесь.**

- **Окружение:**
  - Supabase service role key
  - R2 credentials (account ID, access key, secret key, bucket)
  - OpenRouter API key
  - Datalab API key
  - Redis URL
  - API secret key
- **Компоненты:**
  - `api` — FastAPI (uvicorn), порт 8000, лимит 512 MB
  - `worker` — Celery, лимит 6 GB RAM / 4 CPU
  - `redis` — Redis Alpine, лимит 256 MB
- **Docker:** `infra/backend/docker-compose.yml`
- **Подключается к:** Supabase (Postgres), R2, OpenRouter, LM Studio

### 3. LM Studio Server

Отдельная GPU-машина для локальных LLM моделей.

- **Требования:** GPU 8+ GB VRAM
- **Подключение:** через `CHANDRA_BASE_URL` на backend
- **Документация:** `infra/lmstudio/README.md`

## Схема потоков данных

```
Browser
  │
  ▼
Web (nginx) ──/api/──▶ Backend (FastAPI) ──▶ Supabase (Postgres)
                          │                    R2 (S3)
                          │                    OpenRouter
                          ▼
                     Celery Worker ──▶ те же зависимости
                          │
                          ▼
                     LM Studio (GPU)
```

## Supabase

- **Production:** managed Supabase (supabase.com)
  - Создать проект → получить URL + service_role key
  - Миграции: `supabase db push --linked`
- **Local dev:** Supabase CLI
  - `supabase init` (один раз)
  - `supabase start` → localhost:54321
  - anon_key → frontend .env
  - service_role_key → backend .env
- **Никогда:** не эмулировать Supabase обычным Postgres

## Безопасность

- Frontend **не получает** raw API keys для OpenRouter, LM Studio, R2
- Все запросы к OCR-провайдерам проходят **только через backend**
- Frontend общается с Supabase **только** через anon key + RLS policies
- Backend использует service_role key для административных операций
