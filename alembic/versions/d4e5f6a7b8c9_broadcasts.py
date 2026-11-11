"""Add broadcast audit and queued delivery.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-11-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _has_index(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return name in {index["name"] for index in inspector.get_indexes(table)}


def upgrade() -> None:
    if not _has_table("broadcasts"):
        op.create_table(
            "broadcasts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("created_by", sa.BIGINT(), nullable=False),
            sa.Column("audience", sa.String(length=24), nullable=False, server_default="groups"),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("parse_mode", sa.String(length=16), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
            sa.Column("total_targets", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("broadcasts", "ix_broadcasts_status_created"):
        op.create_index("ix_broadcasts_status_created", "broadcasts", ["status", "created_at"])
    if not _has_index("broadcasts", "ix_broadcasts_creator"):
        op.create_index("ix_broadcasts_creator", "broadcasts", ["created_by", "created_at"])