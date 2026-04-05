-- Индексы для dirty detection и manual_lock фильтрации
-- при smart rerun

-- Блоки без signature — кандидаты на распознавание
CREATE INDEX IF NOT EXISTS idx_blocks_no_signature
    ON blocks(document_id)
    WHERE deleted_at IS NULL AND last_recognition_signature IS NULL;

-- Locked-блоки — пропускаются при smart/full rerun
CREATE INDEX IF NOT EXISTS idx_blocks_locked
    ON blocks(document_id)
    WHERE deleted_at IS NULL AND manual_lock = true;
