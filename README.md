# OCR Web MVP

Web MVP для OCR-системы распознавания документов.  
Монорепозиторий с раздельной продакшен-топологией: Web / Backend / LM Studio.

## Структура

```
apps/web/          — React + TypeScript + Vite + Ant Design (SPA)
services/api/      — FastAPI backend
workers/ocr/       — Celery OCR worker
packages/ocr_core/ — Python-пакет: ядро OCR (модели, crop, render)
packages/contracts/ — Shared schemas (OpenAPI contracts)
docs/              — Документация
scripts/           — Утилиты
infra/             — Docker Compose файлы для каждого сервера
```

## Быстрый старт

### Требования

- Node.js 20+
- Python 3.11+
- Redis (или Docker)
- Supabase CLI (`npm install -g supabase`)

### Установка

```bash
make install          # установить все зависимости
make install-packages # установить shared Python-пакеты
```

### Локальная разработка

```bash
# Терминал 1: Redis
make dev-redis

# Терминал 2: FastAPI
make dev-api

# Терминал 3: Celery worker
make dev-worker

# Терминал 4: Web
make dev-web
```

### Lint & Tests

```bash
make lint   # ruff + mypy + tsc + eslint
make test   # pytest + vitest
```

### Docker (production-like)

```bash
make docker-backend   # FastAPI + Celery + Redis
make docker-web       # nginx + SPA
```

## Продакшен-топология

Три **независимых** сервера:

1. **Web** — nginx + React SPA. Знает только `BACKEND_URL` и Supabase public config.
2. **Backend** — FastAPI + Celery + Redis. Хранит все секреты (Supabase service key, R2, OpenRouter).
3. **LM Studio** — отдельная GPU-машина для локальных LLM моделей.

Подробнее: [docs/deploy-topology.md](docs/deploy-topology.md)

## Block kinds

Только три типа блоков: `text`, `stamp`, `image`.  
Тип `table` удалён полностью.

## Правила

- Prompts — только из БД, не из config/env/frontend
- Source of truth — Postgres/Supabase, не R2
- R2 хранит только: original PDF + финальный crop блока
- Каждый блок распознаётся отдельно (без strips/batches)
- Секреты — только на backend, никогда на frontend
