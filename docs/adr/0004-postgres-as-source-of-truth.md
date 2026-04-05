# ADR-0004: Postgres как единственный source of truth

> Дата: 2026-04-05
> Статус: Принят

## Контекст

В legacy системе есть два конкурирующих source of truth для данных блоков и OCR результатов.

### Источник 1: annotations.data JSONB blob

Таблица `annotations` содержит поле `data JSONB` с полной структурой документа:

```json
{
  "pages": [
    {
      "page_index": 0,
      "page_size": [1200, 1600],
      "blocks": [
        {
          "id": "XXXX-XXXX-XXX",
          "block_type": "text",
          "coords_px": [100, 200, 500, 400],
          "coords_norm": [0.083, 0.125, 0.417, 0.250],
          "ocr_text": "Распознанный текст...",
          "prompt": {"system": "...", "user": "..."}
        }
      ]
    }
  ]
}
```

Проблемы:
- **Весь state в одном поле**: обновление одного блока → перезапись всего blob
- **Race condition**: два параллельных обновления → одно перезатрёт другое
- **Нет гранулярных query**: нельзя сделать `WHERE quality = 'suspicious'` без JSONB extraction
- **Три версии формата** (v0, v1, v2) с миграцией в коде (`annotation_io.py`)
- **Нет транзакций на уровне блоков**

### Источник 2: result.json в R2

`ocr_result_merger.py` генерирует `result.json` через сложный merge:
- Читает `annotation.json` (блоки + координаты)
- Читает `ocr_result.html` (OCR вывод)
- Мержит: для каждого блока ищет HTML-фрагмент по armor ID (fuzzy matching)
- Добавляет `ocr_html`, `ocr_meta`, `crop_url`

`result.json` используется downstream:
- `html_generator.py` читает из result.json для генерации HTML
- `md/generator.py` читает из result.json для генерации Markdown
- Desktop GUI загружает result.json для отображения результатов
- `task_results.py::_generate_correction_results()` скачивает old result.json для merge при коррекции

### Конфликт между источниками

- `annotations.data` — primary для координат и блоков
- `result.json` — primary для OCR текстов и export
- При коррекции: download old result.json → merge new blocks → upload → но annotations.data уже обновлён отдельно
- Нет гарантии consistency между двумя представлениями

## Решение

Postgres — единственный source of truth. Нормализованные таблицы:

```
documents ──1:N──▶ pages ──1:N──▶ blocks ──1:N──▶ ocr_results
```

- **Нет JSONB blob** как primary state
- **Нет result.json** как файл-источник
- R2 хранит только бинарные файлы (PDF, crop images)
- Export генерируется on-demand из SQL query

### Новая модель данных

| Было (legacy) | Стало (web MVP) |
|---------------|-----------------|
| `annotations.data` JSONB (весь документ) | `blocks` таблица (одна строка = один блок) |
| `result.json` файл в R2 | `ocr_results` таблица (одна строка = один результат) |
| `job_files` + `node_files` (каталог файлов) | `r2_crop_key` на блоке + `r2_key` на документе |
| `image_categories` (промпты в category) | `prompts` таблица (ADR-0003) |
| `jobs` (OCR задачи с phase_data) | `ocr_runs` (простой статус + счётчики) |

### Выигрыш в query capability

```sql
-- Все suspicious блоки документа (невозможно в legacy без JSONB extraction)
SELECT b.*, or.quality_score
FROM blocks b
JOIN ocr_results or ON or.block_id = b.id AND or.is_current = TRUE
WHERE b.document_id = $1 AND or.quality_score = 'suspicious';

-- Статистика по engine за последние 24h
SELECT engine, quality_score, COUNT(*)
FROM ocr_results
WHERE created_at > now() - interval '24 hours'
GROUP BY engine, quality_score;

-- Блоки без OCR результата
SELECT b.* FROM blocks b
LEFT JOIN ocr_results or ON or.block_id = b.id AND or.is_current = TRUE
WHERE b.document_id = $1 AND or.id IS NULL;
```

## Последствия

### Положительные
- Гранулярные query по любому полю (block_kind, quality_score, is_dirty, engine)
- Транзакционная целостность: обновление блока + результата атомарно
- RLS для multi-user: `WHERE user_id = auth.uid()` на уровне БД
- Нет race conditions: UPDATE одного блока не затрагивает другие
- Версионирование результатов: `ocr_results` с `is_current` и `attempt_number`
- Export генерируется из актуальных данных (не из потенциально устаревшего файла)

### Отрицательные
- Больше JOIN-ов при чтении (documents → pages → blocks → ocr_results)
- Нет "snapshot" документа — всё живое (mitigation: export фиксирует состояние)
- Миграция legacy данных требует распаковки JSONB blob в отдельные строки

## Альтернативы

| Вариант | Причина отклонения |
|---------|-------------------|
| Сохранить JSONB blob + нормализованные таблицы (dual write) | Дрейф между двумя представлениями, двойная стоимость записи |
| MongoDB для документной модели | Supabase уже выбран, Postgres JSONB достаточен для опциональных полей |
| result.json в R2 как primary + Postgres как cache | R2 не поддерживает query, нет транзакций, нет RLS |
