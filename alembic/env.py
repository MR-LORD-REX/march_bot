from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine, pool

from bot.DB.base import base
from bot.DB import models  # noqa: F401  (register all models)

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

DATABASE_URL = os.getenv("ALEMBIC_DATABASE_URL")
if not DATABASE_URL:
    from bot.config.config import DB_URL

    DATABASE_URL = DB_URL

# Alembic's migration context is synchronous. Do not hand it the app's
# asyncpg URL; use the sync psycopg DBAPI through the same connection string.
sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))

target_metadata = base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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