from sqlalchemy import Boolean, Integer, String, BIGINT, ForeignKey, Index, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from sqlalchemy.sql import func

from DB.base import base


class Report(base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_reporter", "reporter_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporter_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    uid: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    origin_chat_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    origin_message_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    admin_chat_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    admin_message_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    assigned_to: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["ReportMessage"]] = relationship(
        "ReportMessage", back_populates="report", cascade="all, delete-orphan"
    )
    events: Mapped[list["ReportEvent"]] = relationship(
        "ReportEvent", back_populates="report", cascade="all, delete-orphan"
    )


class ReportMessage(base):
    __tablename__ = "report_messages"
    __table_args__ = (
        Index("ix_report_messages_report", "report_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_chat_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    delivery_message_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    report: Mapped["Report"] = relationship("Report", back_populates="messages")


class ReportEvent(base):
    __tablename__ = "report_events"
    __table_args__ = (
        Index("ix_report_events_report", "report_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    report: Mapped["Report"] = relationship("Report", back_populates="events")


class WebSession(base):
    __tablename__ = "web_sessions"
    __table_args__ = (
        Index("ix_web_sessions_user", "telegram_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    telegram_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)