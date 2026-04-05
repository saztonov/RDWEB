"""CLI для миграции данных из legacy OCR-системы в Web MVP.

Использование:
    python -m scripts.migrate_legacy import-prompts   --config-yaml path/to/config.yaml
    python -m scripts.migrate_legacy import-annotation [--node-id UUID] [--limit N]
    python -m scripts.migrate_legacy import-result     [--node-id UUID]
    python -m scripts.migrate_legacy import-all        [--node-id UUID] [--limit N]

Env переменные:
    LEGACY_DATABASE_URL    — PostgreSQL URL legacy БД
    TARGET_DATABASE_URL    — PostgreSQL URL целевой БД
    MIGRATION_WORKSPACE_ID — UUID целевого workspace
    MIGRATION_PROFILE_ID   — UUID document_profile (опционально)
    MIGRATION_USER_ID      — UUID пользователя-мигратора (опционально)
    MIGRATION_ENGINE_MAP   — Маппинг engine→source_id: "openrouter=uuid1,chandra=uuid2"
"""

from __future__ import annotations

import logging
import sys

import click
from dotenv import load_dotenv

from .config import MigrationConfig
from .db import create_clients
from .utils import MigrationState, MigrationSummary, console

load_dotenv()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stderr)],
    )


@click.group()
@click.option("--legacy-db-url", envvar="LEGACY_DATABASE_URL", help="PostgreSQL URL legacy БД")
@click.option("--target-db-url", envvar="TARGET_DATABASE_URL", help="PostgreSQL URL целевой БД")
@click.option("--workspace-id", envvar="MIGRATION_WORKSPACE_ID", help="UUID целевого workspace")
@click.option("--profile-id", envvar="MIGRATION_PROFILE_ID", default=None, help="UUID document_profile")
@click.option("--user-id", envvar="MIGRATION_USER_ID", default=None, help="UUID мигратора")
@click.option("--engine-map", envvar="MIGRATION_ENGINE_MAP", default="", help="openrouter=uuid,chandra=uuid")
@click.option("--dry-run", is_flag=True, default=False, help="Режим имитации (без записи)")
@click.option("--skip-existing", is_flag=True, default=True, help="Пропускать уже импортированные")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Подробный вывод")
@click.option("--state-file", default="scripts/migrate_legacy/.migration_state.json", help="Путь к state файлу")
@click.pass_context
def cli(ctx, legacy_db_url, target_db_url, workspace_id, profile_id, user_id,
        engine_map, dry_run, skip_existing, verbose, state_file):
    """Утилита миграции данных из legacy OCR-системы в Web MVP."""
    _setup_logging(verbose)

    # Парсинг engine_map
    engine_source_map = {}
    if engine_map:
        for pair in engine_map.split(","):
            if "=" in pair:
                k, v = pair.strip().split("=", 1)
                engine_source_map[k.strip()] = v.strip()

    ctx.ensure_object(dict)
    ctx.obj["config"] = MigrationConfig(
        legacy_db_url=legacy_db_url or "",
        target_db_url=target_db_url or "",
        workspace_id=workspace_id or "",
        document_profile_id=profile_id,
        engine_source_map=engine_source_map,
        migrator_user_id=user_id,
        dry_run=dry_run,
        skip_existing=skip_existing,
        verbose=verbose,
        state_file=state_file,
    )


@cli.command("import-prompts")
@click.option("--config-yaml", required=True, type=click.Path(exists=True), help="Путь к legacy config.yaml")
@click.pass_context
def cmd_import_prompts(ctx, config_yaml):
    """Импортировать промпты из legacy config.yaml → prompt_templates."""
    config: MigrationConfig = ctx.obj["config"]
    summary = MigrationSummary()

    if not config.dry_run and not config.target_db_url:
        console.print("[red]Ошибка: TARGET_DATABASE_URL не задан[/red]")
        raise SystemExit(1)

    from .db import DatabaseClient
    from .importers.prompt_importer import import_prompts

    target_db = DatabaseClient(config.target_db_url, "target") if not config.dry_run else None
    if target_db:
        target_db.connect()

    try:
        template_map = import_prompts(config, target_db, summary, config_yaml)
        console.print(f"\n  Template map: {template_map}")
    finally:
        if target_db:
            target_db.close()

    summary.print_report(config.dry_run)


@cli.command("import-annotation")
@click.option("--node-id", default=None, help="UUID конкретного node для миграции")
@click.option("--limit", type=int, default=0, help="Лимит документов (0=все)")
@click.pass_context
def cmd_import_annotation(ctx, node_id, limit):
    """Импортировать annotation.json → documents + pages + blocks."""
    config: MigrationConfig = ctx.obj["config"]
    summary = MigrationSummary()
    state = MigrationState(config.state_file)

    _validate_urls(config)

    legacy_db, target_db = create_clients(config)

    try:
        from .importers.annotation_importer import import_annotations
        block_map = import_annotations(config, legacy_db, target_db, state, summary, node_id, limit)
        console.print(f"\n  Block map size: {len(block_map)}")
    finally:
        legacy_db.close()
        target_db.close()

    if not config.dry_run:
        state.save()

    summary.print_report(config.dry_run)


@cli.command("import-result")
@click.option("--node-id", default=None, help="UUID конкретного node")
@click.pass_context
def cmd_import_result(ctx, node_id):
    """Обогатить blocks данными из result.json + создать recognition_attempts."""
    config: MigrationConfig = ctx.obj["config"]
    summary = MigrationSummary()
    state = MigrationState(config.state_file)

    _validate_urls(config)

    legacy_db, target_db = create_clients(config)

    try:
        from .importers.annotation_importer import import_annotations
        from .importers.result_importer import import_results

        # Нужен block_map — перестроить из state или запустить annotation import
        block_map = _rebuild_block_map(legacy_db, state)

        prompt_map = _load_prompt_map(target_db)

        import_results(config, legacy_db, target_db, state, summary, block_map, prompt_map, node_id)
    finally:
        legacy_db.close()
        target_db.close()

    if not config.dry_run:
        state.save()

    summary.print_report(config.dry_run)


@cli.command("import-all")
@click.option("--node-id", default=None, help="UUID конкретного node")
@click.option("--limit", type=int, default=0, help="Лимит документов (0=все)")
@click.option("--config-yaml", required=True, type=click.Path(exists=True), help="Путь к legacy config.yaml")
@click.pass_context
def cmd_import_all(ctx, node_id, limit, config_yaml):
    """Полная миграция: промпты → аннотации → результаты."""
    config: MigrationConfig = ctx.obj["config"]
    summary = MigrationSummary()
    state = MigrationState(config.state_file)

    _validate_urls(config)

    legacy_db, target_db = create_clients(config)

    try:
        # 1. Промпты
        from .importers.prompt_importer import import_prompts
        prompt_map = import_prompts(config, target_db, summary, config_yaml)

        # 2. Аннотации
        from .importers.annotation_importer import import_annotations
        block_map = import_annotations(config, legacy_db, target_db, state, summary, node_id, limit)

        # 3. Результаты
        from .importers.result_importer import import_results
        import_results(config, legacy_db, target_db, state, summary, block_map, prompt_map, node_id)

    finally:
        legacy_db.close()
        target_db.close()

    if not config.dry_run:
        state.save()

    summary.print_report(config.dry_run)
    console.print(f"\n  State: {state.stats}")


def _validate_urls(config: MigrationConfig) -> None:
    """Проверить что URL-ы БД заданы."""
    if not config.legacy_db_url:
        console.print("[red]Ошибка: LEGACY_DATABASE_URL не задан[/red]")
        raise SystemExit(1)
    if not config.dry_run and not config.target_db_url:
        console.print("[red]Ошибка: TARGET_DATABASE_URL не задан[/red]")
        raise SystemExit(1)


def _rebuild_block_map(legacy_db, state: MigrationState) -> dict[str, dict[str, str]]:
    """Перестроить block_map из state (для import-result без предварительного import-annotation).

    Упрощённая версия — возвращает пустой маппинг.
    Для полноценной работы нужно запускать import-all.
    """
    console.print("  [yellow]Block map перестраивается из state файла (ограниченный режим)[/yellow]")
    return {}


def _load_prompt_map(target_db) -> dict[str, str]:
    """Загрузить маппинг template_key → id из целевой БД."""
    rows = target_db.execute(
        "SELECT id, template_key FROM prompt_templates WHERE template_key LIKE 'legacy_%'"
    )
    return {row["template_key"]: str(row["id"]) for row in rows}
