"""Baseline the pre-Alembic HSR bot schema.

Revision ID: 6067f2697aab
Revises:
Create Date: 2026-11-11

This revision materializes the schema that historically came from
SQLAlchemy ``create_all``. Existing deployments must adopt it without
recreating their tables:

    alembic stamp 6067f2697aab
    alembic upgrade head

Fresh deployments run ``alembic upgrade head`` directly.

The baseline is intentionally frozen DDL rather than a call to
``metadata.create_all``. Model edits must always arrive as a later revision;
otherwise a fresh database and an upgraded database would disagree.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "6067f2697aab"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _create_table(name: str, *columns, **kwargs) -> None:
    if not _has_table(name):
        op.create_table(name, *columns, **kwargs)


def _create_index(name: str, table_name: str, columns, **kwargs) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, **kwargs)


def upgrade() -> None:
    _create_table(
        "users",
        sa.Column("telegram_id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("banned", sa.Boolean(), nullable=False),
        sa.Column("warns", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("telegram_id"),
    )

    _create_table(
        "telegram_groups",
        sa.Column("group_id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("group_name", sa.String(), nullable=True),
        sa.Column("banned", sa.Boolean(), nullable=False),
        sa.Column("lore_spoiler", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("group_id"),
    )

    _create_table(
        "admins",
        sa.Column("telegram_id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column(
            "authority",
            sa.Enum("basic", "moderator", "admin", "owner", name="authority_type"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("telegram_id"),
    )

    _create_table(
        "ai_api",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_name", sa.String(), nullable=False),
        sa.Column("api_key", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_name"),
    )

    _create_table(
        "ai_models",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("rpm", sa.Integer(), nullable=False),
        sa.Column("rpd", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("api_name", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["api_name"], ["ai_api.api_name"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_name", "model_name", name="uq_ai_models_api_model"),
    )

    _create_table(
        "cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BIGINT(), nullable=False),
        sa.Column("file_id", sa.String(length=255), nullable=False),
        sa.Column("data", sa.String(length=800), nullable=True),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column(
            "type",
            sa.Enum("PFP", "CHAR", "MOC", "PF", "ANO", "AS", name="cache_type"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["telegram_id"], ["users.telegram_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(
        "uq_cache_char",
        "cache",
        ["telegram_id", "type", "slot"],
        unique=True,
        postgresql_where=sa.text("type = 'CHAR'"),
    )
    _create_index(
        "uq_cache_non_char",
        "cache",
        ["telegram_id", "type"],
        unique=True,
        postgresql_where=sa.text("type != 'CHAR'"),
    )

    _create_table(
        "commands_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cmd", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cmd"),
    )

    _create_table(
        "game_ids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("game_id", sa.BIGINT(), nullable=False),
        sa.Column("auth_token", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(
        "one_active_idx",
        "game_ids",
        ["user_id", "game_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )

    _create_table(
        "group_command_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.BIGINT(), nullable=False),
        sa.Column("cmd", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["telegram_groups.group_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "cmd", name="uq_group_cmd"),
    )

    _create_table(
        "lore_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("max_turns", sa.Integer(), nullable=False),
        sa.Column("history_ttl", sa.Integer(), nullable=False),
        sa.Column("reply_ttl", sa.Integer(), nullable=False),
        sa.Column("handoff_turns", sa.Integer(), nullable=False),
        sa.Column("rpm_wait", sa.Integer(), nullable=False),
        sa.Column("max_question_len", sa.Integer(), nullable=False),
        sa.Column("user_rpd", sa.Integer(), nullable=False),
        sa.Column("spoiler_default", sa.Boolean(), nullable=False),
        sa.Column("rpd_disabled", sa.Boolean(), nullable=False),
        sa.Column("rpd_disabled_on", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    _create_table(
        "scheduler_meta",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum("Daily", "Weekly", "Oneshot", name="task_type_enum"),
            nullable=False,
        ),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("kwargs", sa.JSON(), nullable=True),
        sa.Column("execution_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )

    _create_table(
        "user_settings",
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("profile_template", sa.Integer(), nullable=False),
        sa.Column("lang", sa.String(), nullable=False),
        sa.Column("character_template", sa.Integer(), nullable=False),
        sa.Column("dalies_reminder", sa.Boolean(), nullable=False),
        sa.Column("weekly_reminder", sa.Boolean(), nullable=False),
        sa.Column("perform_daily", sa.Boolean(), nullable=False),
        sa.Column("benchmark", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    _create_table(
        "users_in_group",
        sa.Column("user_id", sa.BIGINT(), nullable=False),
        sa.Column("group_id", sa.BIGINT(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["telegram_groups.group_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.telegram_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )


def downgrade() -> None:
    op.drop_table("users_in_group")
    op.drop_table("user_settings")
    op.drop_table("scheduler_meta")
    op.drop_table("lore_settings")
    op.drop_table("group_command_settings")
    op.drop_index("one_active_idx", table_name="game_ids")
    op.drop_table("game_ids")
    op.drop_table("commands_meta")
    op.drop_index("uq_cache_non_char", table_name="cache")
    op.drop_index("uq_cache_char", table_name="cache")
    op.drop_table("cache")
    op.drop_table("ai_models")
    op.drop_table("ai_api")
    op.drop_table("admins")
    op.drop_table("telegram_groups")
    op.drop_table("users")

    bind = op.get_bind()
    sa.Enum(name="task_type_enum").drop(bind, checkfirst=True)
    sa.Enum(name="cache_type").drop(bind, checkfirst=True)
    sa.Enum(name="authority_type").drop(bind, checkfirst=True)