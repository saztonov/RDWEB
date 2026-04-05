Роль: Senior AI Fullstack Architect + Senior Python OCR Engineer.

Контекст:
Мы создаём новый web MVP для OCR-системы. Старый проект находится в ./legacy_project/ и используется как reference для переиспользования OCR-ядра, crop/render логики, verification/fallback логики, export logic и UX-паттернов.
Это НЕ desktop-port 1:1. Это новая система.

Язык:
- Все комментарии в коде, commit-like summary, docs и пояснения пиши на русском языке.
- Имена файлов, классов, функций, API routes, env variables и SQL entities оставляй технически уместными.

Жёсткие правила:
1. Block kinds только: text, stamp, image.
2. table удалить полностью. Не оставлять ни в enum, ни в БД, ни в API, ни в UI, ни в queue names, ни в export logic.
3. stamp — отдельный block kind, не image+category_code=stamp.
4. Prompts брать только из БД. Никаких prompt text в config.yaml, settings.py, frontend payload, block payload и env-конфигах, кроме служебных defaults/seed.
5. Source of truth для OCR результатов — Postgres/Supabase, не R2.
6. R2 хранит только:
   - original PDF
   - финальный crop блока после завершения обработки блока
7. Во время OCR промежуточные crop-ы не должны гоняться через R2.
8. Каждый блок распознаётся отдельно. Никаких strips, merged crops, batch OCR нескольких блоков в одном запросе, BLOCK separators и т.п.
9. Smart rerun должен обрабатывать только новые/dirty блоки.
10. Manual edits не должны молча перезаписываться.
11. Сайт, backend и LM Studio должны быть независимыми по deploy.
12. На сайте должна быть admin/ops панель:
   - health panel
   - sources availability
   - recognition runs
   - block incidents
   - logs/events
13. Все секреты только на backend.
14. Frontend не получает raw API keys для OpenRouter, LM Studio, R2.
15. Не использовать annotations.data blob как primary state.
16. Не использовать result.json как primary source of truth.

Что переносить из reference почти без изменений или с адаптацией:
- crop/render идеи из:
  legacy_project/services/remote_ocr/server/pdf_streaming_core.py
- OCR adapters и HTTP util из:
  legacy_project/rd_core/ocr/openrouter.py
  legacy_project/rd_core/ocr/_openrouter_common.py
  legacy_project/rd_core/ocr/chandra.py
  legacy_project/rd_core/ocr/_chandra_common.py
  legacy_project/rd_core/ocr/http_utils.py
- verification/fallback идеи из:
  legacy_project/services/remote_ocr/server/block_verification.py
  legacy_project/services/remote_ocr/server/text_ocr_quality.py
  legacy_project/services/remote_ocr/server/backend_factory.py
  legacy_project/services/remote_ocr/server/circuit_breaker.py
  legacy_project/services/remote_ocr/server/lmstudio_lifecycle.py
  legacy_project/services/remote_ocr/server/memory_utils.py
- export logic идеи из:
  legacy_project/rd_core/ocr/html_generator.py
  legacy_project/rd_core/ocr/md/generator.py
  legacy_project/rd_core/ocr/generator_common.py
- logging/ops идеи из:
  legacy_project/services/remote_ocr/server/logging_config.py
- UX reference из:
  legacy_project/app/gui/page_viewer.py
  legacy_project/app/gui/page_viewer_mouse.py
  legacy_project/app/gui/page_viewer_polygon.py
  legacy_project/app/gui/page_viewer_resize.py
  legacy_project/app/gui/page_viewer_blocks.py
  legacy_project/app/gui/blocks/*
  legacy_project/app/gui/remote_ocr/panel.py
  legacy_project/app/gui/job_details_dialog.py
  legacy_project/app/gui/block_verification_dialog.py

Что использовать только как anti-reference:
- legacy_project/services/remote_ocr/server/pdf_twopass/pass2_strips.py
- legacy_project/services/remote_ocr/server/worker_prompts.py::build_strip_prompt
- legacy_project/services/remote_ocr/server/storage_settings.py prompt lookup from config
- legacy_project/services/remote_ocr/server/config.yaml prompt texts
- legacy_project/services/remote_ocr/server/task_upload.py как модель промежуточных crop uploads
- legacy_project/services/remote_ocr/server/ocr_result_merger.py как primary merge architecture
- legacy_project/services/remote_ocr/server/task_results.py в части result.json как источника истины
- legacy_project/rd_core/models/block.py legacy compatibility around table
- legacy_project/database/migrations/prod.sql в частях image_categories / table_model / jobs as final model
- весь desktop GUI как архитектурную основу

Требования к результату каждого этапа:
1. Перечисли созданные и изменённые файлы.
2. Дай команды запуска и проверки.
3. Если были SQL changes — покажи migration files.
4. Дай manual test checklist.
5. Отдельно перечисли TODO следующего этапа.
6. Ничего не делай “приблизительно”: если в промпте сказано изучить reference-файлы, реально опирайся на них.