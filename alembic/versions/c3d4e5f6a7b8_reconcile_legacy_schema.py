"""Schema reconciliation for databases created before Alembic.

Revision ID: c3d4e5f6a7b8
Revises: 9b2f8a4c1d10
Create Date: 2026-11-11

The production database was created by the old ``create_all`` startup path.
It can legitimately have tables such as ``users`` while missing later model
columns or the report/web tables. This revision makes the upgrade safe to run
against that state: it adds only what is absent and never drops data.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c3d4e5f6a7b8"
down_revision = "9b2f8a4c1d10"
branch_labels = None
depends_on = None


def _column_names(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def _add_missing_columns(table: str, columns: list[sa.Column]) -> None:
    existing = _column_names(table)
    if not existing:
        return
    for column in columns:
        if column.name in existing:
            continue
        op.add_column(table, column)
        op.alter_column(table, column.name, server_default=None)


def upgrade() -> None:
    _add_missing_columns(
        "lore_settings",
        [
            sa.Column("spoiler_default", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("rpd_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("rpd_disabled_on", sa.String(), nullable=True),
        ],
    )

    _add_missing_columns(
        "telegram_groups",
        [sa.Column("lore_spoiler", sa.Boolean(), nullable=True)],
    )
    _add_missing_columns(
        "commands_meta",
        [sa.Column("reason", sa.String(), nullable=True)],
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("reports"):
        op.create_table(
            "reports",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("reporter_id", sa.BIGINT(), nullable=False),
            sa.Column("report_type", sa.String(length=32), nullable=False),
            sa.Column("uid", sa.BIGINT(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
            sa.Column("origin_chat_id", sa.BIGINT(), nullable=True),
            sa.Column("origin_message_id", sa.BIGINT(), nullable=True),
            sa.Column("admin_chat_id", sa.BIGINT(), nullable=True),
            sa.Column("admin_message_id", sa.BIGINT(), nullable=True),
            sa.Column("assigned_to", sa.BIGINT(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["reporter_id"], ["users.telegram_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_reports_status_created", "reports", ["status", "created_at"])
        op.create_index("ix_reports_reporter", "reports", ["reporter_id", "created_at"])

    if not inspector.has_table("report_messages"):
        op.create_table(
            "report_messages",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("author_id", sa.BIGINT(), nullable=True),
            sa.Column("direction", sa.String(length=16), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("delivery_chat_id", sa.BIGINT(), nullable=True),
            sa.Column("delivery_message_id", sa.BIGINT(), nullable=True),
            sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_report_messages_report", "report_messages", ["report_id", "created_at"])

    if not inspector.has_table("report_events"):
        op.create_table(
            "report_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("actor_id", sa.BIGINT(), nullable=True),
            sa.Column("event", sa.String(length=32), nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_report_events_report", "report_events", ["report_id", "created_at"])

    if not inspector.has_table("web_sessions"):
        op.create_table(
            "web_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("telegram_id", sa.BIGINT(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["telegram_id"], ["users.telegram_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_web_sessions_user", "web_sessions", ["telegram_id", "expires_at"])

    if not inspector.has_table("web_handoffs"):
        op.create_table(
            "web_handoffs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("token", sa.String(length=128), nullable=False),
            sa.Column("telegram_id", sa.BIGINT(), nullable=False),
            sa.Column("chat_id", sa.BIGINT(), nullable=False),
            sa.Column("message_id", sa.BIGINT(), nullable=False),
            sa.Column("uid", sa.BIGINT(), nullable=False),
            sa.Column("slot", sa.Integer(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["telegram_id"], ["users.telegram_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token"),
        )
        op.create_index("ix_web_handoffs_user", "web_handoffs", ["telegram_id", "created_at"])


def downgrade() -> None:
    # Reconciliation is intentionally not destructive. A downgrade should
    # never remove tables or columns that may hold production report data.
    pass