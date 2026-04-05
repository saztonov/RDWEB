-- =============================================================================
-- Seed: демо-данные для OCR Web MVP
-- Описание: workspace, профиль, OCR sources, prompt templates, profile routes
-- =============================================================================

-- Фиксированные UUID для воспроизводимости seed-ов
-- Используем детерминистические значения, чтобы seed был идемпотентным

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Demo Workspace
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO workspaces (id, name, slug, settings_json)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Demo Workspace',
    'demo',
    '{"description": "Демонстрационное рабочее пространство для тестирования"}'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Demo Document Profile
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO document_profiles (id, workspace_id, name, description, is_default)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    '00000000-0000-0000-0000-000000000001',
    'Стандартный профиль РД',
    'Профиль по умолчанию для распознавания рабочей документации (РД). Поддерживает text, stamp, image блоки.',
    true
)
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. OCR Sources (3 шт.)
-- ─────────────────────────────────────────────────────────────────────────────

-- OpenRouter — managed API
INSERT INTO ocr_sources (id, source_type, name, base_url, deployment_mode, is_enabled, concurrency_limit, timeout_sec, health_status)
VALUES (
    '00000000-0000-0000-0000-000000000100',
    'openrouter',
    'OpenRouter Cloud',
    'https://openrouter.ai/api/v1',
    'managed_api',
    true,
    8,
    120,
    'unknown'
)
ON CONFLICT DO NOTHING;

-- LM Studio — локальный docker
INSERT INTO ocr_sources (id, source_type, name, base_url, deployment_mode, is_enabled, concurrency_limit, timeout_sec, health_status)
VALUES (
    '00000000-0000-0000-0000-000000000101',
    'lmstudio',
    'LM Studio Local',
    'http://localhost:1234/v1',
    'docker',
    true,
    2,
    180,
    'unknown'
)
ON CONFLICT DO NOTHING;

-- LM Studio — ngrok tunnel
INSERT INTO ocr_sources (id, source_type, name, base_url, deployment_mode, is_enabled, concurrency_limit, timeout_sec, health_status)
VALUES (
    '00000000-0000-0000-0000-000000000102',
    'lmstudio',
    'LM Studio Ngrok',
    'https://example.ngrok-free.app/v1',
    'remote_ngrok',
    false,
    2,
    240,
    'unknown'
)
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Prompt Templates (6 шт.)
--    text/stamp/image × openrouter/lmstudio
--    Это единственный источник промптов — никаких config.yaml или env
-- ─────────────────────────────────────────────────────────────────────────────

-- === TEXT: OpenRouter ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001001',
    'text_openrouter',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'text',
    'openrouter',
    'Ты — OCR-система для распознавания строительной и проектной документации на русском языке. '
    'Извлеки весь текст с изображения точно, сохраняя структуру. '
    'Не добавляй пояснений, не исправляй орфографию, не пропускай технические обозначения.',
    'Распознай текст на изображении. Верни только распознанный текст без каких-либо комментариев.',
    'plain_text',
    'Базовый промпт для текстовых блоков через OpenRouter'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- === TEXT: LM Studio ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001002',
    'text_lmstudio',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'text',
    'lmstudio',
    'Ты — OCR-система для распознавания строительной и проектной документации на русском языке. '
    'Извлеки весь текст с изображения точно, сохраняя структуру. '
    'Не добавляй пояснений, не исправляй орфографию, не пропускай технические обозначения.',
    'Распознай текст на изображении. Верни только распознанный текст без каких-либо комментариев.',
    'plain_text',
    'Базовый промпт для текстовых блоков через LM Studio'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- === STAMP: OpenRouter ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    output_schema_json, parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001003',
    'stamp_openrouter',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'stamp',
    'openrouter',
    'Ты — OCR-система для распознавания штампов и печатей в строительной документации. '
    'Извлеки текст из штампа, включая: название организации, должности, ФИО, даты, номера лицензий. '
    'Сохраняй структуру штампа. Если текст нечитаем — укажи [нечитаемо].',
    'Распознай содержимое штампа/печати на изображении. '
    'Верни структурированный текст штампа, сохраняя иерархию полей.',
    '{"type": "object", "properties": {"organization": {"type": "string"}, "title": {"type": "string"}, "person": {"type": "string"}, "date": {"type": "string"}, "license": {"type": "string"}, "raw_text": {"type": "string"}}}'::jsonb,
    'json_schema',
    'Промпт для штампов/печатей через OpenRouter с JSON-выводом'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- === STAMP: LM Studio ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001004',
    'stamp_lmstudio',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'stamp',
    'lmstudio',
    'Ты — OCR-система для распознавания штампов и печатей в строительной документации. '
    'Извлеки текст из штампа, включая: название организации, должности, ФИО, даты, номера лицензий. '
    'Сохраняй структуру штампа. Если текст нечитаем — укажи [нечитаемо].',
    'Распознай содержимое штампа/печати на изображении. '
    'Верни текст штампа, сохраняя структуру полей. Каждое поле с новой строки.',
    'plain_text',
    'Промпт для штампов/печатей через LM Studio (plain text, без JSON)'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- === IMAGE: OpenRouter ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001005',
    'image_openrouter',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'image',
    'openrouter',
    'Ты — OCR-система для описания графических элементов в строительной документации. '
    'Опиши содержимое изображения: что изображено, какие обозначения присутствуют, '
    'есть ли текстовые подписи или размерные линии. Будь точен и лаконичен.',
    'Опиши содержимое графического блока на чертеже. '
    'Укажи тип изображения (схема, чертёж, фото, диаграмма) и ключевые элементы.',
    'markdown',
    'Промпт для графических блоков через OpenRouter'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- === IMAGE: LM Studio ===
INSERT INTO prompt_templates (
    id, template_key, version, is_active,
    document_profile_id, block_kind, source_type,
    system_template, user_template,
    parser_strategy, notes
)
VALUES (
    '00000000-0000-0000-0000-000000001006',
    'image_lmstudio',
    1,
    true,
    '00000000-0000-0000-0000-000000000010',
    'image',
    'lmstudio',
    'Ты — OCR-система для описания графических элементов в строительной документации. '
    'Опиши содержимое изображения: что изображено, какие обозначения присутствуют, '
    'есть ли текстовые подписи или размерные линии. Будь точен и лаконичен.',
    'Опиши содержимое графического блока на чертеже. '
    'Укажи тип изображения и перечисли основные элементы.',
    'plain_text',
    'Промпт для графических блоков через LM Studio'
)
ON CONFLICT (template_key, version) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. Profile Routes (3 шт. — text/stamp/image)
--    Все маршруты привязаны к стандартному профилю РД
--    Primary source: OpenRouter, fallback: LM Studio Local
-- ─────────────────────────────────────────────────────────────────────────────

-- Route: text → OpenRouter, fallback → LM Studio
INSERT INTO profile_routes (
    id, document_profile_id, block_kind,
    primary_source_id, primary_model_name,
    fallback_chain_json, default_prompt_template_id
)
VALUES (
    '00000000-0000-0000-0000-000000002001',
    '00000000-0000-0000-0000-000000000010',
    'text',
    '00000000-0000-0000-0000-000000000100',
    'google/gemini-2.0-flash-001',
    '[{"source_id": "00000000-0000-0000-0000-000000000101", "model_name": "gemma-3-27b-it", "prompt_template_id": "00000000-0000-0000-0000-000000001002"}]'::jsonb,
    '00000000-0000-0000-0000-000000001001'
)
ON CONFLICT (document_profile_id, block_kind) DO NOTHING;

-- Route: stamp → OpenRouter, fallback → LM Studio
INSERT INTO profile_routes (
    id, document_profile_id, block_kind,
    primary_source_id, primary_model_name,
    fallback_chain_json, default_prompt_template_id
)
VALUES (
    '00000000-0000-0000-0000-000000002002',
    '00000000-0000-0000-0000-000000000010',
    'stamp',
    '00000000-0000-0000-0000-000000000100',
    'google/gemini-2.0-flash-001',
    '[{"source_id": "00000000-0000-0000-0000-000000000101", "model_name": "gemma-3-27b-it", "prompt_template_id": "00000000-0000-0000-0000-000000001004"}]'::jsonb,
    '00000000-0000-0000-0000-000000001003'
)
ON CONFLICT (document_profile_id, block_kind) DO NOTHING;

-- Route: image → OpenRouter, fallback → LM Studio
INSERT INTO profile_routes (
    id, document_profile_id, block_kind,
    primary_source_id, primary_model_name,
    fallback_chain_json, default_prompt_template_id
)
VALUES (
    '00000000-0000-0000-0000-000000002003',
    '00000000-0000-0000-0000-000000000010',
    'image',
    '00000000-0000-0000-0000-000000000100',
    'google/gemini-2.0-flash-001',
    '[{"source_id": "00000000-0000-0000-0000-000000000101", "model_name": "gemma-3-27b-it", "prompt_template_id": "00000000-0000-0000-0000-000000001006"}]'::jsonb,
    '00000000-0000-0000-0000-000000001005'
)
ON CONFLICT (document_profile_id, block_kind) DO NOTHING;
