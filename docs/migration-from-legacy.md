# Миграция данных из Legacy Desktop в OCR Web MVP

> Дата: 2026-04-05
> Статус: Черновик
> Версия: 1.0

---

## Содержание

1. [Предпосылки миграции](#1-предпосылки-миграции)
2. [Маппинг данных](#2-маппинг-данных)
3. [Порядок выполнения](#3-порядок-выполнения)
4. [CLI Usage Guide](#4-cli-usage-guide)
5. [Верификация](#5-верификация)
6. [Known Limitations](#6-known-limitations)
7. [Rollback Plan](#7-rollback-plan)

---

## 1. Предпосылки миграции

### Legacy: PySide6 Desktop + Remote OCR Server

Текущая архитектура: PySide6 desktop-клиент, Celery + LM Studio на удалённом сервере, Supabase DB, Cloudflare R2 storage.

### Проблемы legacy-системы

| Проблема | Описание |
|----------|----------|
| Секреты на клиенте | Supabase anon key, R2 credentials хранятся в `.env` файле desktop-приложения. Любой пользователь имеет доступ к секретам |
| `annotations.data` JSONB blob | Все блоки документа сериализованы в один JSONB blob. Любое изменение одного блока перезаписывает весь blob. Race conditions при параллельной работе |
| Batch strip OCR | TEXT блоки объединяются в strips, отправляются пакетом в LLM. Fuzzy matching armor ID в ответе для разделения результатов по блокам. Хрупкий парсинг, невозможность per-block retry |
| 3 источника промптов | `block.prompt` dict на блоке, `config.yaml` через `storage_settings.py`, `image_categories` таблица в БД. Приоритетная цепочка с дрейфом между источниками |
| `result.json` как SOT | `result.json` в R2 генерируется через `ocr_result_merger.py` (merge annotation.json + ocr_html). Конкурирует с `annotations.data` как source of truth |

### Цели Web MVP

| Цель | Реализация |
|------|-----------|
| Per-block OCR | Один блок = один crop = один API call = один результат. Нет strips, нет batch parsing |
| Postgres SOT | Нормализованные таблицы `blocks` + `recognition_attempts`. Нет JSONB blob, нет result.json |
| Промпты из БД | Единственный источник: таблица `prompt_templates`. Lookup по `block_kind` + `source_type` + `template_key` |
| Workspace multi-tenancy | RLS-политики, `workspace_members`, ролевая модель (owner/admin/member/viewer) |

---

## 2. Маппинг данных

### 2.1 Блоки (blocks)

#### Маппинг block_kind

| Legacy тип | Legacy условие | Web MVP `block_kind` | Примечание |
|-----------|----------------|---------------------|------------|
| TEXT | `block_type = 'TEXT'` | `text` | Прямой маппинг |
| IMAGE | `block_type = 'IMAGE'` AND `category_code = 'stamp'` | `stamp` | Stamp становится first-class kind (см. ADR-0002) |
| IMAGE | `block_type = 'IMAGE'` AND `category_code != 'stamp'` | `image` | Прямой маппинг |
| TABLE | `block_type = 'TABLE'` или `raw_type = 'table'` | **SKIP** | Пропускается с WARNING в логе. В legacy уже конвертировался в TEXT при десериализации |

#### Маппинг координат

| Legacy поле | Web MVP поле | Преобразование |
|------------|-------------|---------------|
| `coords_px` `[x1, y1, x2, y2]` | `bbox_json` `{x, y, width, height}` | `x = x1`, `y = y1`, `width = x2 - x1`, `height = y2 - y1` |
| `polygon_points` (list of tuples) | `polygon_json` (JSONB array) | Прямая сериализация в JSONB |
| `shape_type` = `"rectangle"` | `shape_type` = `'rect'` | Переименование значения enum |
| `shape_type` = `"polygon"` | `shape_type` = `'polygon'` | Без изменений |
| `page_index` (0-based) | `page_number` (1-based) | `page_number = page_index + 1` |

### 2.2 Штампы (stamps)

| Legacy поле | Web MVP поле | Описание |
|------------|-------------|----------|
| `ocr_json` (dict с полями шифр, стадия, организация и т.д.) | `current_structured_json` | Структурированные данные штампа |
| stamp inheritance (export logic) | Сохраняется | Наследование полей штампа на страницы через export logic. Stamp `current_structured_json` используется как header документа при генерации HTML/MD |

### 2.3 OCR результаты

#### Маппинг результатов распознавания

| Legacy источник | Web MVP поле | Описание |
|----------------|-------------|----------|
| `ocr_text` (из annotations.data) | `blocks.current_text` | Текстовый результат OCR |
| `ocr_text` (из annotations.data) | + synthetic `recognition_attempt` | Создается синтетическая запись в `recognition_attempts` с `status='recognized'` |
| `result.json` : `ocr_html` | `recognition_attempts.render_html` | HTML-представление результата |
| `result.json` : `ocr_json` | `recognition_attempts.structured_json` | Структурированный JSON результат |
| `ocr_meta` (quality classifier) | `recognition_attempts.quality_flags_json` | Флаги качества из `text_ocr_quality.classify_text_output()` |

#### Маппинг статусов

| Legacy условие | Web MVP `current_status` |
|---------------|-------------------------|
| `ocr_text` IS NOT NULL и не пустой | `recognized` |
| Ошибка OCR в `ocr_meta` или error flag | `failed` |
| `ocr_text` IS NULL (не обрабатывался) | `pending` |

### 2.4 Промпты (prompt_templates)

| Legacy источник | Web MVP | Описание |
|----------------|---------|----------|
| `config.yaml` : `openrouter_image.system_prompt` | `prompt_templates` record | `template_key = 'legacy_image_openrouter'` |
| `config.yaml` : `openrouter_image.user_prompt` | `prompt_templates` record | Тот же record: `user_template` поле |
| `config.yaml` : `openrouter_stamp.system_prompt` | `prompt_templates` record | `template_key = 'legacy_stamp_openrouter'` |
| `config.yaml` : `openrouter_stamp.user_prompt` | `prompt_templates` record | Тот же record: `user_template` поле |
| `build_strip_prompt()` fallback | `prompt_templates` record | `template_key = 'legacy_text_openrouter'` |

Все импортированные legacy-промпты создаются с параметрами:

- `is_active = false` -- требуют ручной активации после проверки
- `template_key = 'legacy_<kind>_<source>'` -- например `legacy_stamp_openrouter`, `legacy_text_lmstudio`
- `notes = 'Импорт из legacy config.yaml'`
- `version = 1`

---

## 3. Порядок выполнения

### Phase 0: Подготовка

1. **Deploy Web MVP schema** -- применить миграции Supabase:
   ```bash
   supabase db push
   ```

2. **Создать workspace и document_profile** -- через Admin UI или SQL:
   ```sql
   INSERT INTO workspaces (name, slug, created_by)
   VALUES ('Main Workspace', 'main', '<admin_user_id>');

   INSERT INTO workspace_members (workspace_id, user_id, role)
   VALUES ('<ws_id>', '<admin_user_id>', 'owner');

   INSERT INTO document_profiles (workspace_id, name, is_default, created_by)
   VALUES ('<ws_id>', 'Default Profile', true, '<admin_user_id>');
   ```

3. **Настроить `.env`** для скрипта миграции:
   ```env
   LEGACY_DATABASE_URL=postgresql://user:pass@host:5432/legacy_db
   TARGET_DATABASE_URL=postgresql://user:pass@host:5432/web_mvp_db
   TARGET_WORKSPACE_ID=<uuid>
   TARGET_DOCUMENT_PROFILE_ID=<uuid>
   TARGET_USER_ID=<uuid>
   LEGACY_CONFIG_YAML=path/to/config.yaml
   ```

### Phase 1: Импорт промптов

```bash
python -m scripts.migrate_legacy import-prompts \
  --config-yaml path/to/config.yaml
```

Что происходит:
- Парсинг `config.yaml` (openrouter image/stamp system/user prompts)
- Извлечение `build_strip_prompt` fallback текста
- Создание записей в `prompt_templates` с `is_active=false`
- Логирование каждого созданного template_key

### Phase 2: Импорт аннотаций (блоков)

```bash
python -m scripts.migrate_legacy import-annotation \
  [--node-id UUID] \
  [--limit N]
```

Что происходит:
- Чтение `annotations.data` JSONB blob из legacy БД
- Десериализация блоков, конвертация координат
- Маппинг block types (TEXT -> text, IMAGE+stamp -> stamp, IMAGE -> image, TABLE -> SKIP)
- Создание записей в `documents`, `document_pages`, `blocks`

### Phase 3: Импорт результатов OCR

```bash
python -m scripts.migrate_legacy import-result \
  [--node-id UUID]
```

Что происходит:
- Чтение `ocr_text` из legacy `annotations.data`
- Чтение `result.json` из R2 (ocr_html, ocr_json)
- Создание synthetic `recognition_attempts` записей
- Обновление `blocks.current_text`, `blocks.current_status`, `blocks.current_attempt_id`

### Или одной командой

```bash
python -m scripts.migrate_legacy import-all \
  --config-yaml path/to/config.yaml
```

Выполняет Phase 1 -> Phase 2 -> Phase 3 последовательно.

### Общие флаги

| Флаг | Описание |
|------|----------|
| `--dry-run` | Выполняет все операции без записи в целевую БД. Выводит статистику: сколько записей будет создано/пропущено |
| `--skip-existing` | Пропускает записи, которые уже существуют в целевой БД (по legacy ID или armor_id). Безопасно для повторных запусков |
| `--verbose` | Подробный вывод: каждый обработанный блок, каждое преобразование, все warnings |

---

## 4. CLI Usage Guide

### Пример 1: Dry run для оценки объема

```bash
python -m scripts.migrate_legacy import-all \
  --config-yaml ./legacy/config.yaml \
  --dry-run \
  --verbose
```

Ожидаемый вывод:
```
[DRY RUN] Промпты: 5 templates будет создано
[DRY RUN] Документы: 142 documents, 1847 pages
[DRY RUN] Блоки: 12340 text, 284 stamp, 891 image, 23 table (SKIP)
[DRY RUN] Результаты: 11200 recognized, 340 failed, 1975 pending
[DRY RUN] Итого: 0 записей в БД (dry run)
```

### Пример 2: Миграция одного документа для тестирования

```bash
python -m scripts.migrate_legacy import-annotation \
  --node-id 550e8400-e29b-41d4-a716-446655440000 \
  --verbose

python -m scripts.migrate_legacy import-result \
  --node-id 550e8400-e29b-41d4-a716-446655440000 \
  --verbose
```

### Пример 3: Пакетная миграция с ограничением

```bash
python -m scripts.migrate_legacy import-annotation \
  --limit 50 \
  --skip-existing \
  --verbose
```

### Пример 4: Полная миграция

```bash
# 1. Сначала промпты
python -m scripts.migrate_legacy import-prompts \
  --config-yaml ./legacy/config.yaml

# 2. Затем блоки и результаты
python -m scripts.migrate_legacy import-all \
  --config-yaml ./legacy/config.yaml \
  --skip-existing
```

### Пример 5: Повторный запуск после ошибки

```bash
# --skip-existing гарантирует идемпотентность
python -m scripts.migrate_legacy import-all \
  --config-yaml ./legacy/config.yaml \
  --skip-existing \
  --verbose
```

---

## 5. Верификация

После завершения миграции выполните следующие SQL-запросы для проверки целостности данных.

### Количество документов в workspace

```sql
SELECT COUNT(*) AS doc_count
FROM documents
WHERE workspace_id = '<ws_id>';
```

### Блоки по типам

```sql
SELECT block_kind, COUNT(*) AS cnt
FROM blocks
GROUP BY block_kind
ORDER BY cnt DESC;
```

### Orphaned blocks (блоки без документа)

```sql
SELECT COUNT(*) AS orphaned
FROM blocks b
WHERE NOT EXISTS (
    SELECT 1 FROM documents d WHERE d.id = b.document_id
);
```

Ожидаемый результат: `0`. Любое ненулевое значение указывает на проблему с миграцией.

### Блоки в статусе recognized без текста

```sql
SELECT COUNT(*) AS recognized_without_text
FROM blocks
WHERE current_status = 'recognized'
  AND current_text IS NULL;
```

Ожидаемый результат: `0`. Если есть такие блоки -- проверьте логи Phase 3 (import-result).

### Recognition attempts по статусам

```sql
SELECT status, COUNT(*) AS cnt
FROM recognition_attempts
GROUP BY status
ORDER BY cnt DESC;
```

### Сверка количества блоков с legacy

```sql
-- Web MVP
SELECT COUNT(*) AS web_blocks FROM blocks;

-- Legacy (выполнить на legacy БД)
-- Сравнить с результатом, учитывая пропущенные TABLE блоки
SELECT COUNT(*) AS legacy_blocks FROM annotations
WHERE data IS NOT NULL;
```

### Промпты: проверка импорта

```sql
SELECT template_key, version, is_active, block_kind, source_type
FROM prompt_templates
WHERE template_key LIKE 'legacy_%'
ORDER BY template_key;
```

---

## 6. Known Limitations

### TABLE блоки пропускаются

Legacy TABLE блоки не существуют в новой системе (см. [ADR-0002](adr/0002-remove-table-and-make-stamp-first-class.md)). В legacy они уже конвертировались в TEXT при десериализации (`block.py:244`). Скрипт миграции выводит WARNING для каждого пропущенного TABLE блока.

Если TABLE блоки содержали важные данные -- они были распознаны как TEXT в legacy. Результаты OCR для этих блоков доступны в legacy `result.json`, но не переносятся автоматически.

### Tree structure теряется

Legacy использует `tree_nodes` для организации документов в иерархическую структуру (папки, вложенные документы). Web MVP использует flat list документов внутри workspace.

Иерархия не переносится. Все документы попадают в один workspace без вложенности.

### Annotation v0/v1 конвертируются в v2

Legacy имеет три версии формата аннотаций (v0, v1, v2). При миграции v0 и v1 автоматически конвертируются в v2 перед маппингом в Web MVP schema. Конвертация использует ту же логику, что и legacy `block.py` десериализация.

### Strip-level OCR results разбиваются

Legacy объединяет TEXT блоки в strips и получает один OCR-ответ на strip. При миграции результаты разбиваются по block ID с использованием armor ID маркеров из ответа. Если маркеры отсутствуют или повреждены -- блок получает `current_status = 'pending'` и потребует повторного распознавания в Web MVP.

### Промежуточные кропы не переносятся

Legacy хранит в R2 промежуточные crop-файлы (strips, temporary images). Web MVP не использует R2 для промежуточных данных (кропы создаются в `/tmp` на backend и удаляются после OCR). Промежуточные файлы из legacy R2 не переносятся и не удаляются скриптом миграции.

### Привязка к пользователю

Legacy использует `client_id` из локального файла. Web MVP использует Supabase Auth `user_id`. Все мигрированные записи привязываются к `TARGET_USER_ID` из `.env`. Если нужна привязка к разным пользователям -- требуется маппинг `client_id -> user_id`, который скрипт не делает автоматически.

---

## 7. Rollback Plan

### Принципы безопасности

| Принцип | Описание |
|---------|----------|
| Legacy БД read-only | Скрипт миграции только читает из legacy БД, никогда не модифицирует |
| Отдельный Supabase project | Web MVP развёрнут в отдельном Supabase project, не затрагивает legacy данные |
| Идемпотентность | `--skip-existing` позволяет безопасно перезапускать миграцию |

### Откат Web MVP данных

Если миграция выполнена некорректно, можно удалить все мигрированные данные из Web MVP:

```sql
-- ВНИМАНИЕ: удаляет ВСЕ данные в workspace
-- CASCADE удалит documents, blocks, recognition_attempts, и т.д.
DELETE FROM documents WHERE workspace_id = '<ws_id>';

-- Удалить legacy промпты
DELETE FROM prompt_templates WHERE template_key LIKE 'legacy_%';
```

После очистки можно запустить миграцию повторно.

### Точка невозврата

Точка невозврата наступает когда пользователи начинают создавать новые данные в Web MVP:
- Загрузка новых документов
- Ручное редактирование блоков
- Создание новых промптов
- Запуск OCR в Web MVP

После этого откат к legacy невозможен без потери новых данных.

### Параллельная работа (dual-running period)

Параллельная работа legacy desktop и Web MVP возможна:

1. Legacy продолжает работать с legacy Supabase БД
2. Web MVP работает с отдельным Supabase project
3. Новые документы загружаются в Web MVP
4. Legacy данные доступны read-only в обеих системах

Длительность dual-running period определяется командой. Рекомендация: не более 2 недель после начала активного использования Web MVP.

### Мониторинг после миграции

После миграции проверять:
- Логи скрипта на WARNING и ERROR
- SQL-запросы верификации (раздел 5)
- Корректность отображения блоков в Web MVP UI
- Корректность stamp inheritance в export
- Статистику `recognition_attempts` -- количество `pending` блоков, требующих повторного OCR
