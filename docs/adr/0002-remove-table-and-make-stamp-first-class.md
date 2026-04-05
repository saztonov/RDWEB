# ADR-0002: Удаление table и stamp как first-class block kind

> Дата: 2026-04-05
> Статус: Принят

## Контекст

### Table — мёртвый код

В legacy `BlockType` содержит TEXT и IMAGE. Table формально не является отдельным типом, но следы его присутствия разбросаны по системе:

1. `block.py:244` — при десериализации: `if raw_type == "table": block_type = BlockType.TEXT`
2. `job_settings` таблица — поле `table_model` (используется как alias text модели)
3. `prod.sql` — упоминания table в комментариях
4. `backend_factory.py` — `strip` backend обрабатывает TEXT и TABLE одинаково

Table конвертируется в TEXT при каждой загрузке. Нет отдельной OCR модели, промпта или логики для таблиц. LLM-модели (Qwen, Claude, GPT) естественно распознают таблицы в текстовом выводе (HTML `<table>` или Markdown).

### Stamp — скрытый за IMAGE + category_code

В legacy stamp реализован как `IMAGE` с `category_code="stamp"`. Это создаёт условные проверки:

1. `task_upload.py` — `if category_code == "stamp": skip crop upload`
2. `backend_factory.py` — отдельный `stamp_backend` в `JobBackends` dataclass
3. `job_settings` — отдельное поле `stamp_model`
4. `html_generator.py` — специальное форматирование `stamp_data` (шифр, стадия, организация)
5. `md/generator.py` — stamp → header документа, пропуск в теле
6. `block_verification.py` — пропуск stamp блоков при post-OCR verification
7. `worker_prompts.py` — отдельный промпт для stamp category

Stamp семантически отличается от IMAGE: наследование полей на страницы, специальный экспорт, уникальный промпт, исключение из обычного crop workflow.

## Решение

Три block kinds: `text`, `stamp`, `image`.

- `table` удалён полностью — из enum, БД schema, API, UI, queue names, export logic
- `stamp` — first-class kind, не `image + category_code`

```sql
block_kind TEXT NOT NULL CHECK (block_kind IN ('text', 'stamp', 'image'))
```

### Что это меняет

| Было | Стало |
|------|-------|
| `block_type = 'image' AND category_code = 'stamp'` | `block_kind = 'stamp'` |
| `if raw_type == "table": block_type = TEXT` | Нет table вообще |
| `job_settings.table_model` | Удалено |
| `image_categories` таблица для промптов stamp | `prompts` таблица с `block_kind='stamp'` |

## Последствия

### Положительные
- Чистая типизация: `block_kind IN ('text','stamp','image')` — одна проверка вместо двух
- Нет `if category_code == "stamp"` по всему коду
- Stamp имеет собственный UI (форма редактирования полей штампа)
- Stamp имеет собственный промпт в таблице `prompts`
- Stamp имеет собственную export логику (header, а не тело)
- Нет мёртвого кода table

### Отрицательные
- Legacy данные с `table` блоками не импортируются напрямую (нужна миграция → text)
- Legacy данные с `IMAGE + category_code=stamp` не импортируются напрямую (нужна миграция → stamp)

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Сохранить IMAGE + category_code для stamp | Stamp семантически отличается; условные проверки в 7+ местах |
| Добавить TABLE как отдельный kind | LLM распознаёт таблицы как часть text output; отдельный kind не добавляет value |
| Четыре kinds: text, table, stamp, image | Table — мёртвый код, не нужен |
