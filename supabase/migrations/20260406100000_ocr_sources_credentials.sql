-- =============================================================================
-- Миграция: добавление credentials_json в ocr_sources
-- Дата: 2026-04-06
-- Описание: Секреты провайдера хранятся отдельно от capabilities, НЕ отдаются на фронт
-- =============================================================================

ALTER TABLE ocr_sources
    ADD COLUMN credentials_json jsonb DEFAULT '{}'::jsonb;

COMMENT ON COLUMN ocr_sources.credentials_json
    IS 'Секреты провайдера (api_key, auth_user, auth_pass) — НЕ отдавать на фронт';
