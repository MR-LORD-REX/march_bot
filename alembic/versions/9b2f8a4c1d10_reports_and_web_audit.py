"""Add durable report lifecycle and web handoff audit tables.

Revision ID: 9b2f8a4c1d10
Revises: 6067f2697aab
Create Date: 2026-11-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "9b2f8a4c1d10"
down_revision = "6067f2697aab"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _create_table(name: str, *columns, **kwargs) -> None:
    if not _has_table(name):
        op.create_table(name, *columns, **kwargs)


def _create_index(name: str, table_name: str, columns) -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns)


def upgrade() -> None:
    _create_table(
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
    _create_index("ix_reports_status_created", "reports", ["status", "created_at"])
    _create_index("ix_reports_reporter", "reports", ["reporter_id", "created_at"])

    _create_table(
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
    _create_index("ix_report_messages_report", "report_messages", ["report_id", "created_at"])

    _create_table(
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
    _create_index("ix_report_events_report", "report_events", ["report_id", "created_at"])

    _create_table(
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
    _create_index("ix_web_sessions_user", "web_sessions", ["telegram_id", "expires_at"])

    _create_table(
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
    _create_index("ix_web_handoffs_user", "web_handoffs", ["telegram_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_web_handoffs_user", table_name="web_handoffs")
    op.drop_table("web_handoffs")
    op.drop_index("ix_web_sessions_user", table_name="web_sessions")
    op.drop_table("web_sessions")
    op.drop_index("ix_report_events_report", table_name="report_events")
    op.drop_table("report_events")
    op.drop_index("ix_report_messages_report", table_name="report_messages")
    op.drop_table("report_messages")
    op.drop_index("ix_reports_reporter", table_name="reports")
    op.drop_index("ix_reports_status_created", table_name="reports")
    op.drop_table("reports")
