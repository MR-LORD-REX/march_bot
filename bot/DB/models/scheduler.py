from sqlalchemy import String, Integer, Enum, DateTime, JSON, ForeignKey , BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone

from bot.DB.base import base

class SchedulerMeta(base):
    __tablename__ = "scheduler_meta"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BIGINT, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String, unique=True)
    task_name: Mapped[str] = mapped_column(String)
    task_type: Mapped[str] = mapped_column(
        Enum("Daily", "Weekly", "Oneshot", name="task_type_enum")
    )
    args: Mapped[dict] = mapped_column(JSON, nullable=True)
    kwargs: Mapped[dict] = mapped_column(JSON, nullable=True)
    
    execution_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now(timezone.utc)
    )