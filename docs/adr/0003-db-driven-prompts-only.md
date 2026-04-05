# ADR-0003: Промпты только из БД

> Дата: 2026-04-05
> Статус: Принят

## Контекст

В legacy промпты хранятся в трёх конкурирующих источниках:

### Источник 1: block.prompt dict
Промпт хранится внутри блока как `{"system": "...", "user": "..."}`. Сериализуется в `annotations.data` JSONB blob. Используется с наивысшим приоритетом в `worker_prompts.py::get_image_block_prompt()`.

### Источник 2: config.yaml
Промпты для категорий hardcoded в `config.yaml`. Читаются через `storage_settings.py::get_category_prompt()`. Изменение требует redeploy сервера.

### Источник 3: image_categories таблица
Таблица в Postgres с полями `system_prompt`, `user_prompt` по `category_code`. Частично дублирует config.yaml.

### Приоритетная цепочка
`worker_prompts.py::get_image_block_prompt()`:
```python
# Приоритет: block.prompt > category > config.yaml default
if block_prompt:
    return block_prompt
prompt = get_category_prompt(category_id, category_code, engine)  # config.yaml
if not prompt:
    prompt = get_category_from_db(category_code)  # image_categories
return prompt
```

### Variable substitution
`fill_image_prompt_variables()` подставляет переменные:
- `{DOC_NAME}` — имя документа
- `{PAGE_NUM}` — номер страницы (1-based)
- `{BLOCK_ID}` — armor ID блока
- `{OPERATOR_HINT}` — подсказка оператора
- `{PDFPLUMBER_TEXT}` — extracted text из PDF

### Проблемы
1. **Дрейф**: промпт в config.yaml и в image_categories могут расходиться
2. **Redeploy**: изменение промпта в config.yaml требует restart сервера
3. **Неотслеживаемость**: невозможно узнать "какой промпт использовался для этого блока"
4. **Дублирование**: block.prompt дублирует category prompt

## Решение

Единственный источник промптов — таблица `prompts` в Postgres.

```sql
CREATE TABLE prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    block_kind TEXT NOT NULL CHECK (block_kind IN ('text', 'stamp', 'image')),
    category_code TEXT,          -- NULL = default для этого kind
    engine TEXT,                 -- NULL = универсальный, 'chandra', 'openrouter'
    system_prompt TEXT NOT NULL DEFAULT '',
    user_prompt TEXT NOT NULL DEFAULT '',
    is_default BOOLEAN DEFAULT FALSE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(block_kind, category_code, engine)
);
```

### Lookup логика (PromptResolver)

```sql
SELECT * FROM prompts
WHERE block_kind = $1
  AND (category_code = $2 OR category_code IS NULL)
  AND (engine = $3 OR engine IS NULL)
ORDER BY
  category_code DESC NULLS LAST,    -- specific category > default
  engine DESC NULLS LAST            -- specific engine > universal
LIMIT 1;
```

### Variable substitution
Сохраняется без изменений. Переменные `{DOC_NAME}`, `{PAGE_NUM}`, `{BLOCK_ID}`, `{OPERATOR_HINT}`, `{PDFPLUMBER_TEXT}` подставляются в resolved промпт.

### Seed данные
Начальные промпты загружаются SQL миграцией:
```sql
INSERT INTO prompts (block_kind, system_prompt, user_prompt, is_default) VALUES
  ('text', '...', '...', TRUE),
  ('stamp', '...', '...', TRUE),
  ('image', '...', '...', TRUE);
```

### Audit trail
`ocr_results.prompt_id` фиксирует какой промпт использовался для каждого результата.

## Последствия

### Положительные
- Один источник истины для промптов — нет дрейфа
- Промпты меняются через admin UI без redeploy
- Версионирование (`version` поле) для отслеживания изменений
- Audit trail: `ocr_results.prompt_id` → можно узнать какой промпт использовался
- Гранулярность: промпт по block_kind + category_code + engine

### Отрицательные
- Seed данные нужно поддерживать в SQL миграции
- Если БД недоступна — промпты недоступны (нет fallback на файл)

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| config.yaml + env override | Дрейф между файлом и БД, нет UI для редактирования |
| Промпты в frontend payload | Нарушает правило "секреты на backend", prompt injection risk |
| Промпты в block.prompt dict | Дублирование, нет централизованного управления |
| YAML файл + hot reload | Нет UI, нет версионирования, нет audit trail |
