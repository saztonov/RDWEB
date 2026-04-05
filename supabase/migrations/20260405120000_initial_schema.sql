-- =============================================================================
-- Первая миграция: полная схема OCR Web MVP
-- Дата: 2026-04-05
-- Описание: 18 таблиц, 6 enum-типов, RLS-политики, индексы, триггеры
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 0: Extensions
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 1: Enum-типы
-- block_kind: ТОЛЬКО text, stamp, image — БЕЗ table
-- Статусные поля используют text + CHECK для простоты эволюции
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TYPE block_kind    AS ENUM ('text', 'stamp', 'image');
CREATE TYPE shape_type    AS ENUM ('rect', 'polygon');
CREATE TYPE source_type   AS ENUM ('openrouter', 'lmstudio');
CREATE TYPE deployment_mode AS ENUM ('managed_api', 'docker', 'remote_ngrok', 'private_url');
CREATE TYPE run_mode      AS ENUM ('full', 'smart', 'block_rerun');
CREATE TYPE parser_strategy AS ENUM ('plain_text', 'json_schema', 'markdown', 'html', 'regex');

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 2: Helper-функции
-- ─────────────────────────────────────────────────────────────────────────────

-- Автоматическое обновление updated_at через триггер
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- Проверка членства в workspace (для RLS)
-- SECURITY DEFINER — избегаем рекурсии RLS при чтении workspace_members
CREATE OR REPLACE FUNCTION is_workspace_member(ws_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = ws_id
          AND user_id = auth.uid()
    );
$$;

-- Проверка admin/owner роли в workspace
CREATE OR REPLACE FUNCTION is_workspace_admin(ws_id uuid)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.workspace_members
        WHERE workspace_id = ws_id
          AND user_id = auth.uid()
          AND role IN ('owner', 'admin')
    );
$$;

-- Проверка глобального администратора (service_role или is_admin в метаданных)
CREATE OR REPLACE FUNCTION is_global_admin()
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT
        coalesce(auth.jwt() ->> 'role', '') = 'service_role'
        OR coalesce((auth.jwt() -> 'app_metadata' ->> 'is_admin')::boolean, false);
$$;

-- Получение workspace_id документа (для вложенных RLS-проверок)
CREATE OR REPLACE FUNCTION get_document_workspace(doc_id uuid)
RETURNS uuid
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT workspace_id FROM public.documents WHERE id = doc_id;
$$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 3: Workspaces + Members
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE workspaces (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    slug          text UNIQUE NOT NULL,
    settings_json jsonb DEFAULT '{}'::jsonb,
    created_by    uuid REFERENCES auth.users(id),
    updated_by    uuid REFERENCES auth.users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE workspaces IS 'Рабочие пространства — корневая единица изоляции данных';

CREATE TABLE workspace_members (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id      uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role         text NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    invited_by   uuid REFERENCES auth.users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id)
);

COMMENT ON TABLE workspace_members IS 'Участники workspace с ролевой моделью';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 4: Document Profiles + Documents + Pages
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE document_profiles (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name         text NOT NULL,
    description  text,
    is_default   boolean DEFAULT false,
    created_by   uuid REFERENCES auth.users(id),
    updated_by   uuid REFERENCES auth.users(id),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE document_profiles IS 'Профили распознавания — определяют маршруты и промпты для документа';

CREATE TABLE documents (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    title               text NOT NULL,
    original_r2_key     text,
    document_profile_id uuid REFERENCES document_profiles(id) ON DELETE SET NULL,
    status              text NOT NULL DEFAULT 'uploading'
                        CHECK (status IN ('uploading', 'processing', 'ready', 'error', 'archived')),
    page_count          integer DEFAULT 0,
    created_by          uuid REFERENCES auth.users(id),
    updated_by          uuid REFERENCES auth.users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE documents IS 'PDF-документы, загруженные в workspace';

CREATE TABLE document_pages (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number  integer NOT NULL,
    width        integer NOT NULL,
    height       integer NOT NULL,
    rotation     integer DEFAULT 0,
    UNIQUE (document_id, page_number)
);

COMMENT ON TABLE document_pages IS 'Метаданные страниц документа (размеры, ротация)';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 5: OCR Sources + Models Cache
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE ocr_sources (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type       source_type NOT NULL,
    name              text NOT NULL,
    base_url          text NOT NULL,
    deployment_mode   deployment_mode NOT NULL,
    is_enabled        boolean DEFAULT true,
    concurrency_limit integer DEFAULT 4,
    timeout_sec       integer DEFAULT 120,
    health_status     text DEFAULT 'unknown'
                      CHECK (health_status IN ('healthy', 'degraded', 'unavailable', 'unknown')),
    last_health_at    timestamptz,
    capabilities_json jsonb DEFAULT '{}'::jsonb,
    created_by        uuid REFERENCES auth.users(id),
    updated_by        uuid REFERENCES auth.users(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE ocr_sources IS 'Провайдеры OCR (OpenRouter, LM Studio instances)';

CREATE TABLE ocr_source_models_cache (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       uuid NOT NULL REFERENCES ocr_sources(id) ON DELETE CASCADE,
    model_id        text NOT NULL,
    model_name      text NOT NULL,
    context_length  integer,
    supports_vision boolean DEFAULT false,
    extra_json      jsonb,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, model_id)
);

COMMENT ON TABLE ocr_source_models_cache IS 'Кэш доступных моделей для каждого OCR source';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 6: Prompt Templates + Profile Routes
-- Промпты — единственный источник. Никаких prompt text в конфигах.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE prompt_templates (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    template_key        text NOT NULL,
    version             integer DEFAULT 1,
    is_active           boolean DEFAULT true,
    document_profile_id uuid REFERENCES document_profiles(id) ON DELETE SET NULL,
    block_kind          block_kind NOT NULL,
    source_type         source_type NOT NULL,
    model_pattern       text,
    system_template     text NOT NULL,
    user_template       text NOT NULL,
    output_schema_json  jsonb,
    parser_strategy     parser_strategy DEFAULT 'plain_text',
    notes               text,
    created_by          uuid REFERENCES auth.users(id),
    updated_by          uuid REFERENCES auth.users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (template_key, version)
);

COMMENT ON TABLE prompt_templates IS 'Единственный источник промптов для OCR. Версионируются по template_key+version';

CREATE TABLE profile_routes (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_profile_id       uuid NOT NULL REFERENCES document_profiles(id) ON DELETE CASCADE,
    block_kind                block_kind NOT NULL,
    primary_source_id         uuid NOT NULL REFERENCES ocr_sources(id),
    primary_model_name        text NOT NULL,
    fallback_chain_json       jsonb DEFAULT '[]'::jsonb,
    default_prompt_template_id uuid REFERENCES prompt_templates(id) ON DELETE SET NULL,
    created_by                uuid REFERENCES auth.users(id),
    updated_by                uuid REFERENCES auth.users(id),
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_profile_id, block_kind)
);

COMMENT ON TABLE profile_routes IS 'Маршруты распознавания по типу блока в профиле документа';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 7: Blocks + Block Versions
-- blocks — current state блока. Soft delete обязателен.
-- manual_lock, geometry_rev, content_rev обязательны.
-- current_crop_key и crop_upload_state живут в blocks.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE blocks (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id                 uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number                 integer NOT NULL,
    block_kind                  block_kind NOT NULL,
    shape_type                  shape_type DEFAULT 'rect',
    bbox_json                   jsonb,
    polygon_json                jsonb,
    reading_order               integer,
    geometry_rev                integer NOT NULL DEFAULT 1,
    content_rev                 integer NOT NULL DEFAULT 1,
    manual_lock                 boolean NOT NULL DEFAULT false,
    route_source_id             uuid REFERENCES ocr_sources(id),
    route_model_name            text,
    prompt_template_id          uuid REFERENCES prompt_templates(id) ON DELETE SET NULL,
    current_text                text,
    current_structured_json     jsonb,
    current_render_html         text,
    current_status              text NOT NULL DEFAULT 'pending'
                                CHECK (current_status IN (
                                    'pending', 'queued', 'processing',
                                    'recognized', 'failed', 'manual_review', 'skipped'
                                )),
    current_attempt_id          uuid,  -- FK добавляется ниже после создания recognition_attempts
    current_crop_key            text,
    crop_upload_state           text NOT NULL DEFAULT 'none'
                                CHECK (crop_upload_state IN ('none', 'uploading', 'uploaded', 'failed')),
    crop_sha256                 text,
    last_recognition_signature  text,
    created_by                  uuid REFERENCES auth.users(id),
    updated_by                  uuid REFERENCES auth.users(id),
    created_at                  timestamptz NOT NULL DEFAULT now(),
    updated_at                  timestamptz NOT NULL DEFAULT now(),
    deleted_at                  timestamptz  -- soft delete
);

COMMENT ON TABLE blocks IS 'Блоки документа — текущее состояние. Soft delete через deleted_at';
COMMENT ON COLUMN blocks.geometry_rev IS 'Ревизия геометрии — инкрементируется при изменении bbox/polygon';
COMMENT ON COLUMN blocks.content_rev IS 'Ревизия контента — инкрементируется при изменении результатов OCR';
COMMENT ON COLUMN blocks.manual_lock IS 'Ручная блокировка — защита от перезаписи при smart rerun';
COMMENT ON COLUMN blocks.last_recognition_signature IS 'Сигнатура для smart rerun dirty detection';

CREATE TABLE block_versions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id       uuid NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    version_number integer NOT NULL,
    change_type    text NOT NULL
                   CHECK (change_type IN ('geometry', 'route', 'prompt', 'content', 'manual_edit')),
    snapshot_json  jsonb NOT NULL,
    created_by     uuid REFERENCES auth.users(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE block_versions IS 'Snapshot-история изменений блока (geometry/route/prompt/content)';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 8: Recognition Runs + Attempts + Events + Ops
-- recognition_attempts — append-only, никогда не обновляются
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE recognition_runs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id          uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    initiated_by         uuid NOT NULL REFERENCES auth.users(id),
    run_mode             run_mode NOT NULL,
    status               text NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    total_blocks         integer DEFAULT 0,
    dirty_blocks         integer DEFAULT 0,
    processed_blocks     integer DEFAULT 0,
    recognized_blocks    integer DEFAULT 0,
    failed_blocks        integer DEFAULT 0,
    manual_review_blocks integer DEFAULT 0,
    started_at           timestamptz,
    finished_at          timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE recognition_runs IS 'Запуски распознавания документа (full/smart/block_rerun)';

CREATE TABLE recognition_attempts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              uuid NOT NULL REFERENCES recognition_runs(id) ON DELETE CASCADE,
    block_id            uuid NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    geometry_rev        integer NOT NULL,
    source_id           uuid NOT NULL REFERENCES ocr_sources(id),
    model_name          text NOT NULL,
    prompt_template_id  uuid NOT NULL REFERENCES prompt_templates(id),
    prompt_snapshot_json jsonb NOT NULL,
    parser_version      text,
    attempt_no          integer NOT NULL,
    fallback_no         integer DEFAULT 0,
    status              text NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'success', 'failed', 'timeout', 'skipped')),
    normalized_text     text,
    structured_json     jsonb,
    render_html         text,
    quality_flags_json  jsonb,
    raw_response_excerpt text,
    error_code          text,
    error_message       text,
    selected_as_current boolean DEFAULT false,
    started_at          timestamptz,
    finished_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE recognition_attempts IS 'Append-only история попыток распознавания блоков';

-- Отложенный FK: blocks.current_attempt_id → recognition_attempts
ALTER TABLE blocks
    ADD CONSTRAINT fk_blocks_current_attempt
    FOREIGN KEY (current_attempt_id) REFERENCES recognition_attempts(id)
    ON DELETE SET NULL;

-- Audit trail по блокам
CREATE TABLE block_events (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    block_id     uuid NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    event_type   text NOT NULL,
    payload_json jsonb DEFAULT '{}'::jsonb,
    actor_id     uuid REFERENCES auth.users(id),
    created_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE block_events IS 'Аудит-трейл событий по блокам';
COMMENT ON COLUMN block_events.event_type IS 'Типы: created, geometry_changed, recognized, manual_edit, locked, unlocked, deleted, restored';

-- Структурированные операционные события для admin-панели
CREATE TABLE system_events (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type     text NOT NULL,
    severity       text NOT NULL DEFAULT 'info'
                   CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    source_service text,
    payload_json   jsonb DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE system_events IS 'Операционные события системы для admin/ops панели';

-- Health snapshots по сервисам
CREATE TABLE service_health_checks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name    text NOT NULL,
    status          text NOT NULL CHECK (status IN ('healthy', 'degraded', 'unavailable')),
    response_time_ms integer,
    details_json    jsonb,
    checked_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE service_health_checks IS 'Снапшоты здоровья сервисов (backend/redis/supabase/r2/ocr sources)';

-- Heartbeat воркеров
CREATE TABLE worker_heartbeats (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    worker_name  text NOT NULL UNIQUE,
    queue_name   text,
    host         text,
    pid          integer,
    memory_mb    real,
    active_tasks integer DEFAULT 0,
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE worker_heartbeats IS 'Пульс воркеров: queue, host, pid, memory, active tasks';

-- История экспортов документов
CREATE TABLE document_exports (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    export_format text NOT NULL
                  CHECK (export_format IN ('html', 'markdown', 'json', 'pdf')),
    options_json  jsonb DEFAULT '{}'::jsonb,
    r2_key        text,
    file_name     text,
    file_size     bigint,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    error_message text,
    created_by    uuid REFERENCES auth.users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
);

COMMENT ON TABLE document_exports IS 'История экспортов документов с параметрами и метаданными';

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 9: Индексы
-- ─────────────────────────────────────────────────────────────────────────────

-- workspace_members: UNIQUE(workspace_id, user_id) уже создаёт индекс, добавляем только обратный
CREATE INDEX idx_wm_user ON workspace_members(user_id);

-- documents
CREATE INDEX idx_docs_workspace ON documents(workspace_id);
CREATE INDEX idx_docs_profile   ON documents(document_profile_id) WHERE document_profile_id IS NOT NULL;
CREATE INDEX idx_docs_status    ON documents(workspace_id, status);

-- document_pages: UNIQUE(document_id, page_number) уже создаёт индекс

-- document_profiles
CREATE INDEX idx_dp_workspace ON document_profiles(workspace_id);

-- ocr_sources
CREATE INDEX idx_os_enabled ON ocr_sources(source_type) WHERE is_enabled = true;

-- ocr_source_models_cache
CREATE INDEX idx_osmc_source ON ocr_source_models_cache(source_id);

-- prompt_templates
CREATE INDEX idx_pt_active  ON prompt_templates(block_kind, source_type) WHERE is_active = true;
CREATE INDEX idx_pt_profile ON prompt_templates(document_profile_id) WHERE document_profile_id IS NOT NULL;
CREATE INDEX idx_pt_key     ON prompt_templates(template_key);

-- profile_routes
CREATE INDEX idx_pr_profile ON profile_routes(document_profile_id);

-- blocks: partial-индексы учитывают soft delete
CREATE INDEX idx_blocks_doc_page   ON blocks(document_id, page_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_blocks_doc_status ON blocks(document_id, current_status) WHERE deleted_at IS NULL;
CREATE INDEX idx_blocks_dirty      ON blocks(document_id)
    WHERE deleted_at IS NULL AND current_status IN ('pending', 'failed');
CREATE INDEX idx_blocks_deleted    ON blocks(document_id) WHERE deleted_at IS NOT NULL;
CREATE INDEX idx_blocks_reading    ON blocks(document_id, page_number, reading_order)
    WHERE deleted_at IS NULL AND reading_order IS NOT NULL;

-- block_versions
CREATE INDEX idx_bv_block ON block_versions(block_id, version_number);

-- recognition_runs
CREATE INDEX idx_rr_doc    ON recognition_runs(document_id);
CREATE INDEX idx_rr_status ON recognition_runs(document_id, status);

-- recognition_attempts
CREATE INDEX idx_ra_run      ON recognition_attempts(run_id);
CREATE INDEX idx_ra_block    ON recognition_attempts(block_id, attempt_no);
CREATE INDEX idx_ra_selected ON recognition_attempts(block_id) WHERE selected_as_current = true;

-- block_events
CREATE INDEX idx_be_block ON block_events(block_id, created_at);

-- system_events
CREATE INDEX idx_se_type_time ON system_events(event_type, created_at DESC);
CREATE INDEX idx_se_severity  ON system_events(severity, created_at DESC)
    WHERE severity IN ('error', 'critical');

-- service_health_checks
CREATE INDEX idx_shc_service ON service_health_checks(service_name, checked_at DESC);

-- worker_heartbeats
CREATE INDEX idx_wh_last_seen ON worker_heartbeats(last_seen_at DESC);

-- document_exports
CREATE INDEX idx_de_doc ON document_exports(document_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 10: Триггеры updated_at
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TRIGGER trg_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_document_profiles_updated_at
    BEFORE UPDATE ON document_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_ocr_sources_updated_at
    BEFORE UPDATE ON ocr_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_prompt_templates_updated_at
    BEFORE UPDATE ON prompt_templates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_profile_routes_updated_at
    BEFORE UPDATE ON profile_routes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_blocks_updated_at
    BEFORE UPDATE ON blocks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- Секция 11: Row Level Security
-- ─────────────────────────────────────────────────────────────────────────────

-- Включаем RLS на всех таблицах
ALTER TABLE workspaces              ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_members       ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents               ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_pages          ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_sources             ENABLE ROW LEVEL SECURITY;
ALTER TABLE ocr_source_models_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompt_templates        ENABLE ROW LEVEL SECURITY;
ALTER TABLE profile_routes          ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocks                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE block_versions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE recognition_runs        ENABLE ROW LEVEL SECURITY;
ALTER TABLE recognition_attempts    ENABLE ROW LEVEL SECURITY;
ALTER TABLE block_events            ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_events           ENABLE ROW LEVEL SECURITY;
ALTER TABLE service_health_checks   ENABLE ROW LEVEL SECURITY;
ALTER TABLE worker_heartbeats       ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_exports        ENABLE ROW LEVEL SECURITY;

-- ── Группа E: workspaces ────────────────────────────────────────────────────

CREATE POLICY ws_select ON workspaces FOR SELECT
    USING (is_workspace_member(id) OR is_global_admin());

CREATE POLICY ws_insert ON workspaces FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL);

CREATE POLICY ws_update ON workspaces FOR UPDATE
    USING (is_workspace_admin(id) OR is_global_admin());

CREATE POLICY ws_delete ON workspaces FOR DELETE
    USING (is_workspace_admin(id) OR is_global_admin());

-- ── Группа B: workspace_members ─────────────────────────────────────────────

CREATE POLICY wm_select ON workspace_members FOR SELECT
    USING (is_workspace_member(workspace_id) OR is_global_admin());

CREATE POLICY wm_insert ON workspace_members FOR INSERT
    WITH CHECK (is_workspace_admin(workspace_id) OR is_global_admin());

CREATE POLICY wm_update ON workspace_members FOR UPDATE
    USING (is_workspace_admin(workspace_id) OR is_global_admin());

CREATE POLICY wm_delete ON workspace_members FOR DELETE
    USING (is_workspace_admin(workspace_id) OR is_global_admin());

-- ── Группа F: document_profiles ─────────────────────────────────────────────

CREATE POLICY dp_select ON document_profiles FOR SELECT
    USING (is_workspace_member(workspace_id) OR is_global_admin());

CREATE POLICY dp_insert ON document_profiles FOR INSERT
    WITH CHECK (is_workspace_admin(workspace_id) OR is_global_admin());

CREATE POLICY dp_update ON document_profiles FOR UPDATE
    USING (is_workspace_admin(workspace_id) OR is_global_admin());

CREATE POLICY dp_delete ON document_profiles FOR DELETE
    USING (is_workspace_admin(workspace_id) OR is_global_admin());

-- ── Группа A: documents ─────────────────────────────────────────────────────

CREATE POLICY docs_select ON documents FOR SELECT
    USING (is_workspace_member(workspace_id) OR is_global_admin());

CREATE POLICY docs_insert ON documents FOR INSERT
    WITH CHECK (is_workspace_member(workspace_id) OR is_global_admin());

CREATE POLICY docs_update ON documents FOR UPDATE
    USING (is_workspace_member(workspace_id) OR is_global_admin());

CREATE POLICY docs_delete ON documents FOR DELETE
    USING (is_workspace_admin(workspace_id) OR is_global_admin());

-- ── Группа A: document_pages (через documents) ─────────────────────────────

CREATE POLICY dp_pages_select ON document_pages FOR SELECT
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY dp_pages_insert ON document_pages FOR INSERT
    WITH CHECK (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY dp_pages_update ON document_pages FOR UPDATE
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY dp_pages_delete ON document_pages FOR DELETE
    USING (is_workspace_admin(get_document_workspace(document_id)) OR is_global_admin());

-- ── Группа C: ocr_sources — чтение всем, запись админам ─────────────────────

CREATE POLICY os_select ON ocr_sources FOR SELECT
    USING (auth.uid() IS NOT NULL OR is_global_admin());

CREATE POLICY os_insert ON ocr_sources FOR INSERT
    WITH CHECK (is_global_admin());

CREATE POLICY os_update ON ocr_sources FOR UPDATE
    USING (is_global_admin());

CREATE POLICY os_delete ON ocr_sources FOR DELETE
    USING (is_global_admin());

-- ── Группа C: ocr_source_models_cache ───────────────────────────────────────

CREATE POLICY osmc_select ON ocr_source_models_cache FOR SELECT
    USING (auth.uid() IS NOT NULL OR is_global_admin());

CREATE POLICY osmc_insert ON ocr_source_models_cache FOR INSERT
    WITH CHECK (is_global_admin());

CREATE POLICY osmc_update ON ocr_source_models_cache FOR UPDATE
    USING (is_global_admin());

CREATE POLICY osmc_delete ON ocr_source_models_cache FOR DELETE
    USING (is_global_admin());

-- ── Группа C: prompt_templates ──────────────────────────────────────────────

CREATE POLICY pt_select ON prompt_templates FOR SELECT
    USING (auth.uid() IS NOT NULL OR is_global_admin());

CREATE POLICY pt_insert ON prompt_templates FOR INSERT
    WITH CHECK (is_global_admin());

CREATE POLICY pt_update ON prompt_templates FOR UPDATE
    USING (is_global_admin());

CREATE POLICY pt_delete ON prompt_templates FOR DELETE
    USING (is_global_admin());

-- ── Группа C: profile_routes ────────────────────────────────────────────────

CREATE POLICY pr_select ON profile_routes FOR SELECT
    USING (
        is_workspace_member(
            (SELECT dp.workspace_id FROM document_profiles dp WHERE dp.id = document_profile_id)
        )
        OR is_global_admin()
    );

CREATE POLICY pr_insert ON profile_routes FOR INSERT
    WITH CHECK (
        is_workspace_admin(
            (SELECT dp.workspace_id FROM document_profiles dp WHERE dp.id = document_profile_id)
        )
        OR is_global_admin()
    );

CREATE POLICY pr_update ON profile_routes FOR UPDATE
    USING (
        is_workspace_admin(
            (SELECT dp.workspace_id FROM document_profiles dp WHERE dp.id = document_profile_id)
        )
        OR is_global_admin()
    );

CREATE POLICY pr_delete ON profile_routes FOR DELETE
    USING (
        is_workspace_admin(
            (SELECT dp.workspace_id FROM document_profiles dp WHERE dp.id = document_profile_id)
        )
        OR is_global_admin()
    );

-- ── Группа A: blocks (через documents) ─────────────────────────────────────

CREATE POLICY blocks_select ON blocks FOR SELECT
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY blocks_insert ON blocks FOR INSERT
    WITH CHECK (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY blocks_update ON blocks FOR UPDATE
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY blocks_delete ON blocks FOR DELETE
    USING (is_workspace_admin(get_document_workspace(document_id)) OR is_global_admin());

-- ── Группа A: block_versions ────────────────────────────────────────────────

CREATE POLICY bv_select ON block_versions FOR SELECT
    USING (
        is_workspace_member(
            get_document_workspace(
                (SELECT b.document_id FROM blocks b WHERE b.id = block_id)
            )
        )
        OR is_global_admin()
    );

CREATE POLICY bv_insert ON block_versions FOR INSERT
    WITH CHECK (is_global_admin());

-- ── Группа A: recognition_runs ──────────────────────────────────────────────

CREATE POLICY rr_select ON recognition_runs FOR SELECT
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY rr_insert ON recognition_runs FOR INSERT
    WITH CHECK (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY rr_update ON recognition_runs FOR UPDATE
    USING (is_global_admin());

-- ── Группа A: recognition_attempts ──────────────────────────────────────────

CREATE POLICY ra_select ON recognition_attempts FOR SELECT
    USING (
        is_workspace_member(
            get_document_workspace(
                (SELECT b.document_id FROM blocks b WHERE b.id = block_id)
            )
        )
        OR is_global_admin()
    );

CREATE POLICY ra_insert ON recognition_attempts FOR INSERT
    WITH CHECK (is_global_admin());

-- ── Группа A: block_events ──────────────────────────────────────────────────

CREATE POLICY be_select ON block_events FOR SELECT
    USING (
        is_workspace_member(
            get_document_workspace(
                (SELECT b.document_id FROM blocks b WHERE b.id = block_id)
            )
        )
        OR is_global_admin()
    );

CREATE POLICY be_insert ON block_events FOR INSERT
    WITH CHECK (is_global_admin());

-- ── Группа D: system_events — только admin/service ──────────────────────────

CREATE POLICY se_select ON system_events FOR SELECT
    USING (is_global_admin());

CREATE POLICY se_insert ON system_events FOR INSERT
    WITH CHECK (is_global_admin());

-- ── Группа D: service_health_checks ─────────────────────────────────────────

CREATE POLICY shc_select ON service_health_checks FOR SELECT
    USING (is_global_admin());

CREATE POLICY shc_insert ON service_health_checks FOR INSERT
    WITH CHECK (is_global_admin());

-- ── Группа D: worker_heartbeats ─────────────────────────────────────────────

CREATE POLICY wh_select ON worker_heartbeats FOR SELECT
    USING (is_global_admin());

CREATE POLICY wh_insert ON worker_heartbeats FOR INSERT
    WITH CHECK (is_global_admin());

CREATE POLICY wh_update ON worker_heartbeats FOR UPDATE
    USING (is_global_admin());

-- ── Группа A: document_exports ──────────────────────────────────────────────

CREATE POLICY de_select ON document_exports FOR SELECT
    USING (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY de_insert ON document_exports FOR INSERT
    WITH CHECK (is_workspace_member(get_document_workspace(document_id)) OR is_global_admin());

CREATE POLICY de_update ON document_exports FOR UPDATE
    USING (is_global_admin());
