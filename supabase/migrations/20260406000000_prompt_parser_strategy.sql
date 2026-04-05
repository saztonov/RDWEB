-- =============================================================================
-- Миграция: замена enum parser_strategy
-- Старые значения: plain_text, json_schema, markdown, html, regex
-- Новые значения:  plain_text, stamp_json, image_json, html_fragment
-- =============================================================================

-- 1. Создаём новый тип enum
CREATE TYPE parser_strategy_v2 AS ENUM ('plain_text', 'stamp_json', 'image_json', 'html_fragment');

-- 2. Добавляем временную колонку с новым типом
ALTER TABLE prompt_templates
    ADD COLUMN parser_strategy_new parser_strategy_v2 DEFAULT 'plain_text';

-- 3. Маппинг старых значений в новые
UPDATE prompt_templates SET parser_strategy_new = CASE parser_strategy
    WHEN 'plain_text'   THEN 'plain_text'::parser_strategy_v2
    WHEN 'json_schema'  THEN 'stamp_json'::parser_strategy_v2
    WHEN 'markdown'     THEN 'image_json'::parser_strategy_v2
    WHEN 'html'         THEN 'html_fragment'::parser_strategy_v2
    WHEN 'regex'        THEN 'plain_text'::parser_strategy_v2
    ELSE 'plain_text'::parser_strategy_v2
END;

-- 4. Удаляем старую колонку
ALTER TABLE prompt_templates DROP COLUMN parser_strategy;

-- 5. Переименовываем новую колонку
ALTER TABLE prompt_templates RENAME COLUMN parser_strategy_new TO parser_strategy;

-- 6. Устанавливаем NOT NULL и DEFAULT
ALTER TABLE prompt_templates
    ALTER COLUMN parser_strategy SET DEFAULT 'plain_text'::parser_strategy_v2;

-- 7. Удаляем старый тип и переименовываем новый
DROP TYPE parser_strategy;
ALTER TYPE parser_strategy_v2 RENAME TO parser_strategy;
