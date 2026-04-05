# Целевая архитектура Web MVP

> Дата: 2026-04-05  
> Статус: Утверждён  
> Версия: 1.0

## 1. Обзор системы

Три независимых сервера + внешние сервисы:

```
┌──────────────┐     ┌──────────────────┐     ┌────────────────┐
│   Browser    │────▶│  Frontend        │────▶│  Backend       │
│              │     │  (Next.js 15)    │     │  (FastAPI)     │
└──────────────┘     │  Vercel / self   │     │  VPS / VM      │
                     └──────────────────┘     └───────┬────────┘
                                                      │
                                    ┌─────────────────┼─────────────────┐
                                    │                 │                 │
                              ┌─────▼─────┐   ┌──────▼──────┐  ┌──────▼──────┐
                              │ LM Studio │   │  Supabase   │  │ Cloudflare  │
                              │ (GPU srv) │   │  Postgres   │  │     R2      │
                              │ /v1/chat  │   │  + Auth     │  │  Storage    │
                              └───────────┘   └─────────────┘  └─────────────┘
                                                      │
                                              ┌───────▼───────┐
                                              │  OpenRouter   │
                                              │  API (cloud)  │
                                              └───────────────┘
```

### Роли серверов

| Сервер | Технология | Роль | Секреты |
|--------|-----------|------|---------|
| Frontend | Next.js 15 (App Router) | UI, SSR/SSG, PDF viewer, block editor, admin panel | Только `NEXT_PUBLIC_API_URL` |
| Backend | FastAPI + uvicorn | API, OCR pipeline, crop, export, auth proxy | Все: Supabase service key, R2 creds, OpenRouter key, LM Studio URL |
| LM Studio | Standalone (GPU) | Локальная LLM, OpenAI-compatible API | Нет (изолирован) |

---

## 2. Компонентная схема

### Frontend (Next.js)

```
app/
├── (auth)/
│   ├── login/page.tsx
│   └── register/page.tsx
├── documents/
│   ├── page.tsx                    # Список документов
│   └── [id]/
│       ├── page.tsx                # Документ viewer + block editor
│       └── export/page.tsx         # Preview export
├── admin/
│   ├── page.tsx                    # Health dashboard
│   ├── sources/page.tsx            # Sources availability
│   ├── runs/page.tsx               # Recognition runs
│   ├── incidents/page.tsx          # Block incidents
│   └── events/page.tsx             # Events log
└── layout.tsx

components/
├── pdf/
│   ├── PDFViewer.tsx               # pdf.js рендеринг
│   ├── BlockOverlay.tsx            # Canvas overlay для блоков
│   ├── BlockDrawTool.tsx           # Рисование rect/polygon
│   └── BlockEditor.tsx             # Редактирование блока (coords, kind, hint)
├── ocr/
│   ├── OCRRunButton.tsx            # Запуск OCR
│   ├── OCRProgress.tsx             # SSE прогресс
│   └── OCRResultPreview.tsx        # Preview результата
├── admin/
│   ├── HealthCard.tsx              # Карточка сервиса
│   ├── SourceStatus.tsx            # Статус OCR бэкенда
│   ├── RunRow.tsx                  # Строка run в таблице
│   ├── IncidentRow.tsx             # Строка incident
│   └── EventRow.tsx                # Строка event с expandable payload
└── shared/
    ├── CopyButton.tsx              # Копирование ID
    └── StatusBadge.tsx             # Статус иконка + текст

lib/
├── api.ts                          # Fetch wrapper → Backend API
├── auth.ts                         # Supabase Auth client (JWT only)
└── stores/
    ├── documentStore.ts            # Zustand: текущий документ
    └── blocksStore.ts              # Zustand: блоки + selection state
```

### Backend (FastAPI)

```
app/
├── main.py                         # FastAPI app, CORS, startup
├── config.py                       # Settings (env vars)
├── dependencies.py                 # Dependency injection
│
├── api/
│   ├── auth.py                     # Login, register, refresh (proxy to Supabase)
│   ├── documents.py                # CRUD documents, upload PDF
│   ├── blocks.py                   # CRUD blocks, coords validation
│   ├── ocr.py                      # Run OCR, progress SSE, cancel
│   ├── results.py                  # Get/edit OCR results
│   ├── export.py                   # Export HTML/MD
│   ├── prompts.py                  # CRUD prompts (admin)
│   └── admin.py                    # Health, sources, runs, incidents, events
│
├── ocr/
│   ├── pipeline.py                 # Per-block OCR orchestrator
│   ├── adapters/
│   │   ├── base.py                 # OCRBackend ABC
│   │   ├── openrouter.py           # OpenRouter adapter (reuse legacy)
│   │   └── chandra.py              # LM Studio adapter (reuse legacy)
│   ├── factory.py                  # Backend factory + fallback chain
│   ├── circuit_breaker.py          # CircuitBreaker (reuse legacy)
│   ├── quality.py                  # Text quality classifier (reuse legacy)
│   └── verification.py             # Post-OCR retry missing blocks
│
├── crop/
│   ├── processor.py                # StreamingPDFProcessor (reuse legacy)
│   └── utils.py                    # Координатные утилиты (px↔norm)
│
├── prompts/
│   └── resolver.py                 # PromptResolver: lookup + variable substitution
│
├── export/
│   ├── html.py                     # HTML generator (reuse legacy)
│   └── markdown.py                 # Markdown generator (reuse legacy)
│
├── storage/
│   └── r2.py                       # R2 client: upload PDF, upload crop, presigned URL
│
├── events/
│   └── logger.py                   # EventLogger: write to events table
│
├── db/
│   ├── session.py                  # asyncpg connection pool
│   ├── queries/                    # SQL queries by domain
│   └── models.py                   # Pydantic models (request/response)
│
└── migrations/
    ├── 001_initial.sql             # Начальная schema
    └── 002_seed_prompts.sql        # Seed данные для промптов
```

---

## 3. Data Flow

### Flow 1: Upload PDF

```
User выбирает PDF → Frontend POST /api/documents/upload (multipart)
  ↓
Backend:
  1. Validate file (PDF, size limit)
  2. Upload PDF to R2 → r2_key = "documents/{user_id}/{uuid}.pdf"
  3. Open PDF with PyMuPDF → extract page_count, page dimensions
  4. INSERT documents (name, r2_key, page_count, file_size)
  5. INSERT pages (document_id, page_index, width_px, height_px) × page_count
  6. Emit event: document_uploaded
  7. Return document_id + page_count
```

### Flow 2: Create / Edit Blocks

```
User рисует блок на canvas → Frontend POST /api/documents/{id}/blocks
  body: { page_index, block_kind, coords_px, coords_norm, shape_type, polygon_points? }
  ↓
Backend:
  1. Validate: block_kind IN (text, stamp, image), coords in page bounds
  2. Generate armor_id (XXXX-XXXX-XXX)
  3. INSERT blocks (page_id, document_id, block_kind, coords_px, coords_norm, ...)
  4. Return block with id + armor_id

User редактирует блок → Frontend PATCH /api/blocks/{id}
  body: { coords_px?, coords_norm?, hint?, block_kind? }
  ↓
Backend:
  1. UPDATE blocks SET ... , is_dirty = TRUE, updated_at = now()
  2. Return updated block
```

### Flow 3: Run OCR

```
User нажимает "Распознать" → Frontend POST /api/ocr/run
  body: { document_id, block_ids?: [...], force?: false }
  ↓
Backend:
  1. SELECT blocks WHERE document_id = $1
     AND (block_ids filter OR is_dirty = TRUE)
     AND (force OR is_manual_edit = FALSE)
  2. INSERT ocr_runs (document_id, user_id, total_blocks, status='running')
  3. Запуск async pipeline (background task)
  4. Return run_id

Frontend подписывается: GET /api/ocr/runs/{run_id}/progress (SSE)

Pipeline (async, per-block):
  for each block:
    ┌─────────────────────────────────────────────────────┐
    │ 1. Crop: StreamingPDFProcessor.crop_block_image()   │
    │    → PIL Image в памяти или /tmp/ocr_{run_id}/      │
    │                                                     │
    │ 2. Resolve prompt:                                  │
    │    SELECT FROM prompts WHERE block_kind = $1         │
    │    AND (category_code = $2 OR IS NULL)               │
    │    AND (engine = $3 OR IS NULL)                      │
    │    → fill_variables({DOC_NAME}, {PAGE_NUM}, ...)     │
    │                                                     │
    │ 3. OCR:                                             │
    │    backend = factory.get_backend(block_kind, engine) │
    │    result = backend.recognize(crop, prompt)          │
    │    → if circuit_breaker.is_open → try fallback       │
    │                                                     │
    │ 4. Quality check:                                   │
    │    quality = classify_text_output(result)            │
    │    → if suspicious → retry with fallback backend     │
    │                                                     │
    │ 5. Save result:                                     │
    │    UPDATE ocr_results SET is_current=FALSE           │
    │      WHERE block_id = $1                             │
    │    INSERT ocr_results (block_id, ocr_text, engine,   │
    │      quality_score, attempt_number, is_current=TRUE) │
    │    UPDATE blocks SET is_dirty=FALSE                  │
    │                                                     │
    │ 6. Upload crop (image/stamp only):                  │
    │    R2.upload(crop, "crops/{block_id}.pdf")           │
    │    UPDATE blocks SET r2_crop_key = ...               │
    │                                                     │
    │ 7. Emit event: ocr_block_completed                  │
    │ 8. SSE: send progress update                        │
    └─────────────────────────────────────────────────────┘

  Cleanup: rm -rf /tmp/ocr_{run_id}/
  UPDATE ocr_runs SET status='done', completed_at=now()
  Emit event: ocr_run_completed
```

### Flow 4: Export

```
User нажимает "Экспорт HTML" → Frontend GET /api/documents/{id}/export?format=html
  ↓
Backend:
  1. SELECT b.*, or.ocr_text, or.ocr_json
     FROM blocks b
     LEFT JOIN ocr_results or ON or.block_id = b.id AND or.is_current = TRUE
     WHERE b.document_id = $1
     ORDER BY p.page_index, b.coords_px[2]  -- top-to-bottom
  2. Generate HTML/MD using adapted generators
  3. Return file (Content-Disposition: attachment)
```

---

## 4. API Structure

### Auth
```
POST   /api/auth/login            # Email/password → JWT
POST   /api/auth/register         # Регистрация
POST   /api/auth/refresh          # Refresh token
```

### Documents
```
GET    /api/documents              # Список документов пользователя
POST   /api/documents/upload       # Upload PDF (multipart)
GET    /api/documents/{id}         # Метаданные документа + pages
DELETE /api/documents/{id}         # Удаление документа + блоков + результатов
```

### Blocks
```
GET    /api/documents/{id}/blocks  # Все блоки документа (с текущими результатами)
POST   /api/documents/{id}/blocks  # Создать блок
PATCH  /api/blocks/{id}            # Обновить блок (coords, kind, hint)
DELETE /api/blocks/{id}            # Удалить блок
```

### OCR
```
POST   /api/ocr/run                # Запустить OCR { document_id, block_ids?, force? }
GET    /api/ocr/runs/{id}          # Статус run
GET    /api/ocr/runs/{id}/progress # SSE stream прогресса
POST   /api/ocr/runs/{id}/cancel   # Отменить run
```

### Results
```
GET    /api/blocks/{id}/result     # Текущий OCR результат блока
PATCH  /api/blocks/{id}/result     # Manual edit { ocr_text, ocr_json? }
GET    /api/blocks/{id}/history    # Все версии результатов блока
```

### Export
```
GET    /api/documents/{id}/export?format=html|md  # Скачать export файл
```

### Prompts (admin)
```
GET    /api/prompts                # Список промптов
POST   /api/prompts               # Создать промпт
PATCH  /api/prompts/{id}          # Обновить промпт
DELETE /api/prompts/{id}          # Удалить промпт
```

### Admin
```
GET    /api/admin/health           # Статус всех сервисов
GET    /api/admin/sources          # OCR бэкенды: статус, latency, circuit state
GET    /api/admin/runs             # Текущие и завершённые OCR runs
GET    /api/admin/incidents        # Блоки с quality suspicious/error
GET    /api/admin/events           # Filtered events log
```

---

## 5. DB Schema

```sql
-- ============================================================
-- Документы
-- ============================================================
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    name TEXT NOT NULL,
    r2_key TEXT NOT NULL,                    -- path to PDF in R2
    page_count INTEGER,
    file_size BIGINT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_documents_user ON documents(user_id);

-- ============================================================
-- Страницы
-- ============================================================
CREATE TABLE pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_index INTEGER NOT NULL,             -- 0-based
    width_px INTEGER NOT NULL,
    height_px INTEGER NOT NULL,
    UNIQUE(document_id, page_index)
);

-- ============================================================
-- Блоки
-- ============================================================
CREATE TABLE blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    armor_id TEXT NOT NULL UNIQUE,            -- XXXX-XXXX-XXX (для display и LLM маркеров)
    page_id UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_kind TEXT NOT NULL CHECK (block_kind IN ('text', 'stamp', 'image')),
    source TEXT NOT NULL DEFAULT 'user' CHECK (source IN ('user', 'auto')),
    shape_type TEXT NOT NULL DEFAULT 'rectangle' CHECK (shape_type IN ('rectangle', 'polygon')),
    coords_px INTEGER[4] NOT NULL,           -- {x1, y1, x2, y2}
    coords_norm FLOAT[4] NOT NULL,           -- {x1, y1, x2, y2} normalized 0..1
    polygon_points JSONB,                    -- [[x1,y1], [x2,y2], ...] для polygon
    hint TEXT,                               -- подсказка оператора
    pdfplumber_text TEXT,                    -- extracted text из PDF
    linked_block_id UUID REFERENCES blocks(id),  -- image → text связь
    r2_crop_key TEXT,                        -- финальный crop в R2 (NULL до OCR)
    is_dirty BOOLEAN DEFAULT TRUE,           -- нуждается в (повторном) OCR
    sort_order INTEGER DEFAULT 0,            -- порядок на странице
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_blocks_document ON blocks(document_id);
CREATE INDEX idx_blocks_page ON blocks(page_id);
CREATE INDEX idx_blocks_dirty ON blocks(document_id, is_dirty) WHERE is_dirty = TRUE;

-- ============================================================
-- OCR результаты (версионирование)
-- ============================================================
CREATE TABLE ocr_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id UUID NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    ocr_text TEXT,                           -- распознанный текст / HTML
    ocr_json JSONB,                          -- parsed entities (image/stamp)
    engine TEXT NOT NULL,                    -- 'chandra', 'openrouter'
    model_name TEXT,                         -- конкретная модель
    quality_score TEXT DEFAULT 'pending'
        CHECK (quality_score IN ('pending', 'good', 'suspicious', 'error')),
    attempt_number INTEGER DEFAULT 1,
    is_manual_edit BOOLEAN DEFAULT FALSE,    -- ручное редактирование
    is_current BOOLEAN DEFAULT TRUE,         -- текущий (последний) результат
    prompt_id UUID,                          -- какой промпт использовался
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_ocr_results_block ON ocr_results(block_id);
CREATE INDEX idx_ocr_results_current ON ocr_results(block_id, is_current) WHERE is_current = TRUE;

-- ============================================================
-- Промпты (единый источник)
-- ============================================================
CREATE TABLE prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_kind TEXT NOT NULL CHECK (block_kind IN ('text', 'stamp', 'image')),
    category_code TEXT,                      -- NULL = default для этого kind
    engine TEXT,                             -- NULL = универсальный
    system_prompt TEXT NOT NULL DEFAULT '',
    user_prompt TEXT NOT NULL DEFAULT '',
    is_default BOOLEAN DEFAULT FALSE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(block_kind, category_code, engine)
);

-- ============================================================
-- OCR runs (группировка запусков)
-- ============================================================
CREATE TABLE ocr_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'done', 'error', 'cancelled')),
    total_blocks INTEGER DEFAULT 0,
    processed_blocks INTEGER DEFAULT 0,
    engine TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_ocr_runs_document ON ocr_runs(document_id);
CREATE INDEX idx_ocr_runs_status ON ocr_runs(status) WHERE status = 'running';

-- ============================================================
-- Events (structured logging для admin панели)
-- ============================================================
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,                -- 'ocr_block_completed', 'source_down', etc.
    severity TEXT DEFAULT 'info'
        CHECK (severity IN ('info', 'warning', 'error')),
    document_id UUID,
    block_id UUID,
    run_id UUID,
    engine TEXT,
    payload JSONB DEFAULT '{}',             -- произвольные метаданные
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_type ON events(event_type, created_at DESC);
CREATE INDEX idx_events_severity ON events(severity, created_at DESC);
CREATE INDEX idx_events_created ON events(created_at DESC);

-- ============================================================
-- RLS Policies
-- ============================================================
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_runs ENABLE ROW LEVEL SECURITY;

-- Пользователь видит только свои документы
CREATE POLICY documents_user_policy ON documents
    FOR ALL USING (user_id = auth.uid());

-- Блоки/страницы/результаты — через принадлежность документу
CREATE POLICY pages_user_policy ON pages
    FOR ALL USING (document_id IN (SELECT id FROM documents WHERE user_id = auth.uid()));

CREATE POLICY blocks_user_policy ON blocks
    FOR ALL USING (document_id IN (SELECT id FROM documents WHERE user_id = auth.uid()));

CREATE POLICY ocr_results_user_policy ON ocr_results
    FOR ALL USING (block_id IN (
        SELECT b.id FROM blocks b
        JOIN documents d ON d.id = b.document_id
        WHERE d.user_id = auth.uid()
    ));

CREATE POLICY ocr_runs_user_policy ON ocr_runs
    FOR ALL USING (user_id = auth.uid());

-- Events доступны только admin (через service key на backend)
-- Frontend admin панель запрашивает через backend API

-- ============================================================
-- Triggers
-- ============================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_updated_at BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER blocks_updated_at BEFORE UPDATE ON blocks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER prompts_updated_at BEFORE UPDATE ON prompts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## 6. Технологический стек

| Layer | Технология | Версия | Назначение |
|-------|-----------|--------|------------|
| **Frontend** | Next.js (App Router) | 15.x | SSR/SSG, routing, API proxy |
| | React | 19.x | UI компоненты |
| | React Query | 5.x | Server state, caching, SSE |
| | Zustand | 5.x | Client state (selection, draw mode) |
| | pdf.js | latest | PDF рендеринг в canvas |
| | Tailwind CSS | 4.x | Стилизация |
| **Backend** | FastAPI | 0.115+ | REST API, SSE, background tasks |
| | uvicorn | latest | ASGI сервер |
| | PyMuPDF (fitz) | latest | PDF rendering, crop |
| | Pillow | latest | Image processing |
| | httpx | latest | Async HTTP client (OpenRouter, LM Studio) |
| | asyncpg | latest | Postgres async driver |
| | aioboto3 | latest | R2 async client |
| | pydantic | 2.x | Request/response validation |
| **LM Studio** | LM Studio | latest | Локальная LLM (Chandra model) |
| **Infrastructure** | Supabase | hosted | Postgres + Auth + RLS |
| | Cloudflare R2 | hosted | Object storage (PDF, crops) |
| | OpenRouter | hosted | Cloud LLM API (fallback) |

---

## 7. Диаграмма зависимостей backend-модулей

```
api/documents ──▶ storage/r2 (upload PDF)
api/documents ──▶ crop/processor (extract page dimensions)

api/blocks ──▶ db/queries (CRUD blocks)

api/ocr ──▶ ocr/pipeline ──▶ crop/processor (crop block)
                          ──▶ prompts/resolver (lookup + fill variables)
                          ──▶ ocr/factory ──▶ ocr/adapters/openrouter
                          │               ──▶ ocr/adapters/chandra
                          │               ──▶ ocr/circuit_breaker
                          ──▶ ocr/quality (classify output)
                          ──▶ ocr/verification (retry suspicious)
                          ──▶ storage/r2 (upload final crop)
                          ──▶ events/logger (emit events)
                          ──▶ db/queries (save results)

api/export ──▶ export/html (generate HTML)
           ──▶ export/markdown (generate MD)
           ──▶ db/queries (SELECT blocks + results)

api/admin ──▶ ocr/circuit_breaker (get states)
          ──▶ events/logger (query events)
          ──▶ db/queries (runs, incidents)

api/prompts ──▶ db/queries (CRUD prompts)
```
