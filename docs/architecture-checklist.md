# Architecture Checklist — OCR Web MVP

> Дата: 2026-04-05
> Версия: 1.0
> Обновляется при каждом sprint review

---

## Секция A: Что уже реализовано

### A.1 Database Schema (18 таблиц)

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Начальная миграция | Готово | 20260405120000_initial_schema.sql |
| 6 enum-типов | Готово | block_kind, shape_type, source_type, deployment_mode, run_mode, parser_strategy |
| Workspaces + members | Готово | Ролевая модель: owner/admin/member/viewer |
| Document profiles | Готово | Профили распознавания для маршрутизации |
| Documents + pages | Готово | PDF metadata, page dimensions, rotation |
| OCR sources + models cache | Готово | Registry pattern, health probes, fallback chains |
| Prompt templates | Готово | Версионирование template_key+version, UNIQUE constraint |
| Profile routes | Готово | block_kind -> source + model + prompt |
| Blocks | Готово | Soft delete, geometry_rev, content_rev, manual_lock |
| Block versions | Готово | Snapshot-based change history |
| Recognition runs + attempts | Готово | full/smart/block_rerun modes, append-only attempts |
| Block events | Готово | Audit trail по блокам |
| System events | Готово | Операционные события (debug..critical) |
| Service health checks | Готово | Снапшоты здоровья по сервисам |
| Worker heartbeats | Готово | Пульс воркеров (memory, tasks) |
| Document exports | Готово | HTML/Markdown generation history |
| RLS policies | Готово | На всех 18 таблицах (is_workspace_member, is_global_admin) |
| Partial indexes | Готово | Soft delete, dirty detection, reading order |
| Миграция parser_strategy | Готово | 20260406000000 |
| Credentials в ocr_sources | Готово | 20260406100000 |
| Dirty detection indexes | Готово | 20260407000000 |
| Seed data | Готово | Demo workspace, 3 OCR sources, 6 промптов, 3 profile routes |

### A.2 Backend API (FastAPI)

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Lifespan инициализация | Готово | Supabase, R2Client, PdfCacheManager, SourceRegistry |
| Health endpoints | Готово | /health (liveness), /health/ready (readiness), /queue |
| Auth layer | Готово | Supabase JWT, CurrentUser, require_admin |
| Permissions | Готово | Audit logging, workspace-scoped access |
| CORS middleware | Готово | Dev: localhost:3000 |
| Documents CRUD | Готово | Upload PDF, page extraction, finalize |
| Blocks CRUD | Готово | Create/update/delete/restore + geometry_rev logic |
| Manual edit + lock | Готово | content_rev++, manual_lock=true, protected from rerun |
| Block prompt override | Готово | Admin-only, per-block template assignment |
| Recognition start | Готово | full/smart/block_rerun через Celery tasks |
| Exports | Готово | HTML + Markdown из Postgres SELECT |
| Prompt templates CRUD | Готово | Versioning, clone, activate, usage analytics |
| Profile routes | Готово | List + update default_prompt_template_id |
| OCR sources admin | Готово | CRUD + health check trigger |
| Admin health dashboard | Готово | Сводный health + queue + workers |
| Admin runs | Готово | Пагинация + детали с блоками |
| Admin incidents | Готово | Failed/timeout attempts с контекстом |
| Admin events | Готово | Фильтруемые system_events + JSONB search |
| Admin SSE | Готово | Redis pub/sub -> 4 канала real-time |
| Dirty detection service | Готово | Smart rerun: только новые/dirty блоки |
| Recognition signature | Готово | Idempotency check |
| R2 client | Готово | S3-compatible, presigned URLs |
| Export service | Готово | HTML + MD генерация |
| Prompt resolver | Готово | Template variable substitution |
| Source registry | Готово | OCR provider lifecycle + health |

### A.3 Worker (Celery)

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Celery config | Готово | Redis broker, acks_late, visibility 24h |
| Block recognizer | Готово | crop -> signature -> route -> OCR -> verify -> write |
| Page processor | Готово | Per-page orchestration |
| Route resolver | Готово | Source + model + fallback chain |
| Prompt resolver | Готово | DB lookup + variable substitution |
| Signature check | Готово | Smart rerun idempotency |
| Quality checks | Готово | Verification pipeline |
| Health probe | Готово | Periodic source healthcheck (1 min) |
| Heartbeat | Готово | Worker liveness (30 sec) |
| Retention cleanup | Готово | Auto-delete old events/checks (daily) |
| Model sync | Готово | Refresh ocr_source_models_cache |
| R2 uploader | Готово | Финальный crop upload |
| Event writer | Готово | Structured event logging |
| Circuit breaker | Готово | Protection from cascading failures |
| Memory utils | Готово | Monitoring + MAX_TASKS_PER_CHILD |

### A.4 Frontend (React SPA)

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Vite + React 18 + TS | Готово | Ant Design UI kit |
| API client | Готово | apiFetch() с JWT injection |
| Auth flow | Готово | Login (Supabase signInWithPassword), ProtectedRoute, Logout, JWT в localStorage |
| Dashboard | Готово | Статистика workspace, последние документы, health overview |
| Document editor | Готово | Split view: PDF canvas + inspector |
| PDF viewer | Готово | pdfjs-dist, multi-page rendering |
| Block overlay | Готово | SVG: rect, polygon, labels, selection |
| Block drawing | Готово | DrawingPreview, ResizeHandles, PolygonHandles |
| Block inspector | Готово | Edit, lock, attempts, prompt override |
| Editor toolbar | Готово | Actions: OCR (Smart/Full), Export (HTML/Markdown dropdown), block ops |
| Admin overview | Готово | Health cards, queue, workers |
| Admin sources | Готово | OCR source status, models cache |
| Admin runs | Готово | List + detail pages |
| Admin incidents | Готово | Failed blocks monitoring |
| Admin events | Готово | System events log |
| Prompt management | Готово | Templates list + detail (CRUD) |
| Zustand stores | Готово | useEditorStore, useAdminStore |
| SSE integration | Готово | useAdminSSE hook |
| Documents list page | Готово | Таблица документов, пагинация, навигация в editor |
| Document upload flow | Готово | Presigned URL → PUT в R2 → finalize → redirect |
| Workspace hook | Готово | Auto-select первого workspace, localStorage persistence |
| Export UI | Готово | Dropdown HTML/Markdown в toolbar, blob download |
| Keyboard shortcuts | Готово | useKeyboardShortcuts hook |
| Autosave | Готово | useAutosave hook |

### A.5 Infrastructure

| Компонент | Статус | Детали |
|-----------|--------|--------|
| Docker Compose backend | Готово | api + worker + redis |
| Docker Compose web | Готово | nginx + SPA dist |
| Nginx config | Готово | SPA fallback, API proxy, SSE, cache |
| Makefile | Готово | install, lint, test, dev-*, docker-* |
| .env.example | Готово | Все переменные задокументированы |
| check_env.py | Готово | Проверка обязательных env переменных |

### A.6 Документация

| Компонент | Статус | Детали |
|-----------|--------|--------|
| ADR 0001-0007 | Готово | 7 архитектурных решений |
| Gap analysis | Готово | Полный маппинг legacy -> new (85+ пунктов) |
| Target architecture | Готово | Компонентная схема, data flows, API, DB |
| Deploy topology | Готово | Трёхсерверная топология |
| Contracts package | Готово | Shared Pydantic schemas для API |
| OCR core package | Готово | Models, cropper, providers, circuit breaker |
| Operations guide | Готово | Runbooks, health checks, monitoring |
| Admin panel guide | Готово | 8 страниц admin UI |
| Migration guide | Готово | Legacy -> MVP маппинг, CLI usage |
| Deployment guides | Готово | Web, Backend, LM Studio |
| Architecture checklist | Готово | Этот документ |

### A.7 Migration Tooling

| Компонент | Статус | Детали |
|-----------|--------|--------|
| CLI utility | Готово | scripts/migrate_legacy/ (Click) |
| import-prompts | Готово | config.yaml -> prompt_templates |
| import-annotation | Готово | annotations -> documents/pages/blocks |
| import-result | Готово | result.json -> recognition_attempts |
| import-all | Готово | Оркестратор полной миграции |
| Dry-run mode | Готово | Имитация без записи |
| Incremental import | Готово | State файл + skip-existing |
| Транзакционность | Готово | psycopg2 BEGIN/COMMIT/ROLLBACK per document |

---

## Секция B: Что осталось после MVP

### B.1 User-Facing Features

| Фича | Приоритет | Комментарий |
|------|-----------|-------------|
| OAuth providers (Google, GitHub) | Средний | Сейчас только email/password |
| Workspace invitation flow UI | Средний | Модель ролей готова, нет UI |
| Document list: фильтрация, сортировка, поиск | Средний | Базовый список реализован, нужны фильтры/поиск |
| Batch document upload | Низкий | Сейчас по одному |
| PDF annotation preview (overlay) | Средний | Результаты OCR поверх PDF |
| Export в PDF формат | Низкий | HTML/MD есть |
| Block auto-detection (ML layout) | Высокий | Ручная разметка сейчас |
| Collaborative editing | Низкий | Supabase Realtime готов |
| Mobile responsive layout | Низкий | Desktop-first |
| Keyboard shortcut customization | Низкий | Дефолтные есть |

### B.2 Admin Features

| Фича | Приоритет | Комментарий |
|------|-----------|-------------|
| OCR source CRUD из UI | Средний | Сейчас через seed/SQL |
| User management panel | Средний | List, assign roles, block |
| Cost tracking (OpenRouter tokens) | Высокий | Нет контроля расходов |
| A/B testing промптов | Низкий | Dual run с двумя templates |
| Scheduled OCR runs (batch queue) | Средний | Сейчас только manual trigger |

### B.3 Infrastructure

| Фича | Приоритет | Комментарий |
|------|-----------|-------------|
| CI/CD pipeline (GitHub Actions) | Высокий | Manual deploy сейчас |
| Staging environment | Высокий | Нет pre-production testing |
| Automated Supabase backup | Высокий | Managed daily backup есть |
| Log aggregation (ELK/Loki) | Средний | Docker json-file сейчас |
| External monitoring (Grafana) | Средний | Admin panel только |
| Rate limiting | Высокий | Нет защиты от abuse |
| Horizontal scaling (API) | Средний | Single instance |
| Horizontal scaling (workers) | Средний | Single worker node |
| R2 CDN | Низкий | Direct R2 access |
| Database connection pooling | Средний | pgBouncer/Supavisor |

### B.4 OCR Pipeline

| Фича | Приоритет | Комментарий |
|------|-----------|-------------|
| Datalab integration | Средний | Третий OCR provider |
| OCR result caching | Низкий | Identical crop → skip |
| Priority queue | Средний | Urgent documents first |
| Webhook notifications | Низкий | При завершении OCR run |
| Per-block progress SSE | Средний | Сейчас per-run только |

---

## Секция C: Риски, перенесённые в post-MVP

### C.1 Performance

| Риск | Вероятность | Влияние | Mitigation | Post-MVP Action |
|------|-------------|---------|------------|-----------------|
| RLS performance на больших workspace (100+ docs, 10K+ blocks) | Средняя | Высокое | Partial indexes, SECURITY DEFINER functions | Benchmark, materialized views |
| SSE через Redis pub/sub — SPOF | Низкая | Среднее | Keepalive + auto-reconnect на frontend | Redis Sentinel или Supabase Realtime |
| Worker memory leaks при долгом аптайме | Средняя | Среднее | MAX_TASKS_PER_CHILD=50, 6 GB limit | Alerting по heartbeat memory_mb |

### C.2 Security

| Риск | Вероятность | Влияние | Mitigation | Post-MVP Action |
|------|-------------|---------|------------|-----------------|
| SSE auth через query param (token в URL) | Низкая | Среднее | HTTPS, admin-only endpoint | Supabase Realtime (WebSocket auth) |
| Нет rate limiting — DDoS/abuse | Средняя | Высокое | Admin-only OCR, workspace isolation | API rate limiting per user/workspace |
| service_role key compromise = full DB | Низкая | Критическое | Key только на backend | Минимизировать usage, user-scoped calls |

### C.3 Operations

| Риск | Вероятность | Влияние | Mitigation | Post-MVP Action |
|------|-------------|---------|------------|-----------------|
| Нет automated backups — data loss | Низкая | Критическое | Supabase managed backups (daily) | Cross-region backup, R2 backup |
| Нет CI/CD — manual deploy ошибки | Средняя | Среднее | make lint + make test | GitHub Actions pipeline |
| Single worker — crash = OCR down | Средняя | Высокое | restart always, heartbeat monitoring | Multiple workers, autoscaler |
| LM Studio single instance — GPU failure | Средняя | Среднее | Fallback chain + circuit breaker | Second instance, cloud GPU |

### C.4 Data Integrity

| Риск | Вероятность | Влияние | Mitigation | Post-MVP Action |
|------|-------------|---------|------------|-----------------|
| Concurrent block edits | Средняя | Среднее | geometry_rev + content_rev (schema ready) | Optimistic locking в handlers, conflict UI |
| recognition_attempts unbounded growth | Высокая | Низкое | Append-only by design | Retention для старых attempts |
| Migration data mismatch | Средняя | Среднее | Dry-run + verification queries | Automated validation suite |

---

## Санитарные проверки (подтверждены 2026-04-05)

| # | Проверка | Результат |
|---|----------|-----------|
| 1 | Нет strip merging logic в кодовой базе | Чисто |
| 2 | Нет table как доменной сущности | Чисто (+ guard-тесты) |
| 3 | Промпты только из БД | Чисто |
| 4 | result.json не используется как source of truth | Чисто (Postgres only) |
| 5 | Intermediate crops не загружаются в R2 | Чисто (только /tmp) |
