from sqlalchemy import Integer, String, Boolean, BIGINT, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.DB.base import base


class GroupCommandSettings(base):
    """Per-group override for one command.

    A row exists only when a group admin has explicitly set the command, so
    "no row" means "inherit the bot-wide default". That keeps the table small
    and makes a newly added command enabled everywhere without a backfill.
    """

    __tablename__ = "group_command_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        BIGINT,
        ForeignKey("telegram_groups.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    cmd: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("group_id", "cmd", name="uq_group_cmd"),
    )

    group: Mapped["TeleGroup"] = relationship(
        "TeleGroup", back_populates="command_settings"
    )
