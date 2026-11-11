from __future__ import annotations

import logging
from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from DB.base import base
from DB import models  # noqa: F401  (register all ORM models)
from shared.config.settings import AUTO_MIGRATE, DB_URL

logger = logging.getLogger(__name__)

BASELINE_REVISION = "6067f2697aab"
ADVISORY_LOCK_KEY = 0x48535242  # "HSRB"

# Tables that belong to the pre-Alembic schema. If at least one exists while
# alembic_version does not, this is a legacy database to adopt, not a fresh one.
_LEGACY_TABLES = {"users", "admins", "game_ids", "telegram_groups"}


def sync_database_url(url: str | None = None) -> str:
    value = url or DB_URL
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        value = value.replace(prefix, "postgresql+psycopg://")
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _alembic_config(url: str | None = None) -> Config:
    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option(
        "sqlalchemy.url", sync_database_url(url or DB_URL).replace("%", "%%")
    )
    return config


def _head_revision(config: Config) -> str | None:
    head = ScriptDirectory.from_config(config).get_current_head()
    return head


def _current_revision(connection) -> str | None:
    if not inspect(connection).has_table("alembic_version"):
        return None
    return connection.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar()


def _adopt_legacy(connection, config: Config) -> None:
    """Replay only absent baseline objects on a pre-Alembic database.

    ``6067f2697aab`` and ``9b2f8a4c1d10`` are idempotent: their helpers create
    tables/indexes only when they are absent and never drop or empty an
    existing table. Alembic advances ``alembic_version`` normally while this
    runs; the caller then upgrades the remaining revisions to head.
    """
    supply_connection = config.attributes.get("connection")
    config.attributes["connection"] = connection
    try:
        alembic_command.upgrade(config, "9b2f8a4c1d10")
    finally:
        if supply_connection is None:
            config.attributes.pop("connection", None)
        else:
            config.attributes["connection"] = supply_connection


def ensure_schema_ready(url: str | None = None) -> None:
    """Adopt a legacy schema if needed and upgrade to Alembic head.

    A database already at head only runs the read-only verification path. This
    keeps normal restarts fast and avoids noisy Alembic output when nothing is
    pending. The caller is responsible for invoking this before the bot or API
    starts; failures are raised so traffic is never served against a stale
    schema.
    """
    if not AUTO_MIGRATE:
        logger.info("AUTO_MIGRATE is disabled; assuming migrations ran externally")
        return

    database_url = sync_database_url(url)
    config = _alembic_config(database_url)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            # Session-level advisory lock serialises concurrent app starts
            # and survives the separate connections Alembic manages.
            connection.execute(
                text("SELECT pg_advisory_lock(:key)"),
                {"key": ADVISORY_LOCK_KEY},
            )
            try:
                tables = set(inspect(connection).get_table_names())
                current = _current_revision(connection)
                head = _head_revision(config)

                if current and head and current == head:
                    logger.info("database already at Alembic head %s", current)
                else:
                    if current is None:
                        legacy = tables & _LEGACY_TABLES
                        if legacy:
                            logger.warning(
                                "legacy database detected (%s); adopting baseline %s",
                                ", ".join(sorted(legacy)),
                                BASELINE_REVISION,
                            )
                            _adopt_legacy(connection, config)
                            connection.commit()
                        else:
                            logger.info("fresh database detected; creating full schema")

                    alembic_command.upgrade(config, "head")
            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": ADVISORY_LOCK_KEY},
                )
                connection.commit()
    finally:
        engine.dispose()

    verify_schema(database_url)


def verify_schema(url: str) -> None:
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            missing_models = set(base.metadata.tables) - tables
            if missing_models:
                raise RuntimeError(
                    "database schema is incomplete after migration; missing: "
                    + ", ".join(sorted(missing_models))
                )
            if "lore_settings" in tables:
                columns = {
                    column["name"] for column in inspector.get_columns("lore_settings")
                }
                required = {"spoiler_default", "rpd_disabled", "rpd_disabled_on"}
                missing = required - columns
                if missing:
                    raise RuntimeError(
                        "lore_settings is missing columns: " + ", ".join(sorted(missing))
                    )
            current = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            if not current:
                raise RuntimeError("alembic_version is empty after migration")
            logger.info("database schema ready at revision %s", current)
    except SQLAlchemyError as exc:
        raise RuntimeError("could not verify database schema after migration") from exc
    finally:
        engine.dispose()