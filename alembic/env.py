from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from DB.base import base
from DB import models  # noqa: F401  (register all models)

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)


def _sync_url(value: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgres://"):
        value = value.replace(prefix, "postgresql+psycopg://")
    if value.startswith("postgresql://"):
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _configured_url() -> str:
    # Programmatic callers (application bootstrap, tests) set the URL on the
    # Alembic Config. Only fall back to ALEMBIC_DATABASE_URL/settings when the
    # config still contains the inert placeholder from alembic.ini.
    configured = config.get_main_option("sqlalchemy.url")
    if configured and configured != "driver://user:pass@localhost/dbname":
        return configured.replace("%%", "%")

    database_url = os.getenv("ALEMBIC_DATABASE_URL")
    if not database_url:
        from shared.config.settings import DB_URL

        database_url = DB_URL
    return _sync_url(database_url)


sync_url = _sync_url(_configured_url())
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))

target_metadata = base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        context.configure(
            connection=supplied,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()