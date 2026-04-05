# ADR-0006: Трёхсерверная топология

> Дата: 2026-04-05
> Статус: Принят

## Контекст

### Legacy архитектура (2 компонента)

```
Desktop Client (PySide6)        Remote OCR Server
├── GUI (Qt widgets)             ├── FastAPI (HTTP API)
├── PDF viewer (QGraphicsView)   ├── Celery (task queue)
├── Block editor                 ├── Redis (broker + state)
├── Supabase client (direct)     ├── LM Studio (local GPU)
├── R2 client (direct)           └── Worker processes
└── OpenRouter client (direct)
```

Desktop клиент имеет прямой доступ ко всем сервисам:
- Supabase anon key для чтения/записи БД
- R2 credentials для upload/download файлов
- OpenRouter API key для fallback OCR

Remote OCR Server = FastAPI + Celery + Redis + LM Studio на одной машине.

### Проблемы для web

1. **Секреты на клиенте**: Supabase anon key, R2 credentials, OpenRouter API key → в web это неприемлемо (DevTools → Network → все ключи)
2. **Монолит OCR сервера**: FastAPI + Celery + Redis + LM Studio на одной машине → GPU и CPU конкурируют за ресурсы
3. **Celery overhead**: prefork модель, Redis broker → для per-block OCR это overkill
4. **Нет frontend server**: desktop GUI → нужен web server для SSR/static

### Требования web MVP

- Frontend не должен иметь секретов (кроме публичного API URL)
- LM Studio требует GPU (отдельный сервер)
- Backend должен проксировать все внешние сервисы
- Каждый компонент обновляется и масштабируется независимо

## Решение

Три независимых сервера:

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │     │   Backend       │     │   LM Studio     │
│   Next.js 15    │────▶│   FastAPI       │────▶│   GPU Server    │
│                 │     │                 │     │                 │
│ Vercel / self   │     │ VPS / VM        │     │ GPU machine     │
│                 │     │                 │     │                 │
│ Секреты: нет    │     │ Секреты: все    │     │ Секреты: нет    │
│ (только API_URL)│     │ - Supabase key  │     │ (изолирован)    │
│                 │     │ - R2 creds      │     │                 │
│                 │     │ - OpenRouter key │     │ OpenAI-compat   │
│                 │     │ - LM Studio URL │     │ /v1/chat/compl  │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌───▼───┐ ┌──────▼──────┐
              │ Supabase  │ │  R2   │ │ OpenRouter  │
              │ Postgres  │ │       │ │ (fallback)  │
              │ + Auth    │ │       │ │             │
              └───────────┘ └───────┘ └─────────────┘
```

### Сервер 1: Frontend (Next.js)

| Параметр | Значение |
|----------|---------|
| Технология | Next.js 15 (App Router) |
| Deploy | Vercel (recommended) или self-hosted |
| Ресурсы | CPU, RAM (SSR rendering) |
| Переменные среды | `NEXT_PUBLIC_API_URL` — единственная |
| Обязанности | UI, SSR/SSG, PDF viewer (pdf.js), block editor (Canvas), admin panel |
| Не делает | Прямые запросы к Supabase/R2/OpenRouter/LM Studio |

### Сервер 2: Backend (FastAPI)

| Параметр | Значение |
|----------|---------|
| Технология | FastAPI + uvicorn |
| Deploy | VPS / VM с достаточным disk space для /tmp |
| Ресурсы | CPU, RAM, disk (temp crops) |
| Переменные среды | Supabase service key, R2 credentials, OpenRouter API key, LM Studio URL |
| Обязанности | REST API, OCR pipeline, crop/render, export, auth proxy, event logging |
| Подключения | Supabase (asyncpg), R2 (aioboto3), OpenRouter (httpx), LM Studio (httpx) |

### Сервер 3: LM Studio (GPU)

| Параметр | Значение |
|----------|---------|
| Технология | LM Studio (standalone) |
| Deploy | GPU сервер (24GB+ VRAM для Chandra model) |
| Ресурсы | GPU, VRAM |
| API | OpenAI-compatible `/v1/chat/completions` |
| Network | Backend подключается напрямую (direct IP или VPN, не ngrok в production) |
| Lifecycle | Может перезагружаться без влияния на web frontend |

### Что убрано из инфраструктуры

| Legacy компонент | Почему убран |
|------------------|-------------|
| Celery | Per-block OCR не требует distributed task queue; async FastAPI достаточно |
| Redis | Нет Celery broker; circuit breaker state — in-memory; нет LM Studio lifecycle coordination |
| ngrok | Production: direct IP/VPN; dev: localhost |

## Последствия

### Положительные
- **Независимый deploy**: обновление frontend (Vercel redeploy) не требует restart backend
- **Изоляция секретов**: frontend не имеет API ключей; LM Studio не имеет DB credentials
- **GPU отдельно**: LM Studio на GPU machine, backend на CPU machine — нет конкуренции
- **LM Studio restart**: перезагрузка модели / обновление LM Studio не роняет web
- **Упрощение**: нет Celery, нет Redis — меньше движущихся частей
- **Масштабирование**: frontend на Vercel → auto-scale; backend → вертикальное; LM Studio → отдельный GPU

### Отрицательные
- **3 сервера вместо 2**: больше инфраструктуры для мониторинга
- **Network latency**: Frontend → Backend → LM Studio = два hop (mitigation: LM Studio latency >>100ms, дополнительный hop незначителен)
- **CORS**: Frontend на другом домене → CORS middleware на backend

### Dev environment
- Все три сервера на localhost (разные порты):
  - Frontend: `localhost:3000`
  - Backend: `localhost:8000`
  - LM Studio: `localhost:1234`

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Monolith (Next.js API routes + OCR) | Node.js не может запустить PyMuPDF; нет Python OCR pipeline |
| Backend + LM Studio на одной машине | GPU и CPU конкурируют; LM Studio restart → backend downtime |
| Microservices (отдельный crop, prompt, export) | Overengineering для MVP; усложняет deploy и debugging |
| Serverless functions | Cold start ~10s; OCR pipeline требует persistent state (PDF in memory) |
| Backend + Celery + Redis (как legacy) | Per-block OCR не требует distributed queue; unnecessary complexity |
