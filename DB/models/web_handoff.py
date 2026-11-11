from sqlalchemy import DateTime, BIGINT, Integer, String, ForeignKey, Index, Index, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from sqlalchemy.sql import func

from DB.base import base


class WebHandoff(base):
    """Durable counterpart to the Redis handoff used by the Mini App.

    Redis is the enforcement store for short-lived claims; this table leaves
    an audit trail of which origin message a web action was allowed to edit.
    """

    __tablename__ = "web_handoffs"
    __table_args__ = (
        Index("ix_web_handoffs_user", "telegram_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    telegram_id: Mapped[int] = mapped_column(BIGINT, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)
    chat_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    message_id: Mapped[int] = mapped_column(BIGINT, nullable=False)
    uid: Mapped[int] = mapped_column(BIGINT, nullable=False)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)