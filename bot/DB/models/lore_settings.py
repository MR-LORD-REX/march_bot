from sqlalchemy import Integer, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from bot.DB.base import base


class LoreSettings(base):
    """Single-row (id=1) tunables for the lore chatbot, editable by admins
    at runtime via /lore_config. Kept in the DB rather than config.py so a
    limit change survives a restart without a redeploy."""

    __tablename__ = "lore_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # conversation memory
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    history_ttl: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    # how long a bot answer stays reply-addressable
    reply_ttl: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    # turns lifted from another user's thread when they reply to that answer
    handoff_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # quota behaviour
    rpm_wait: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    max_question_len: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    # per-user daily cap, counted separately from the API pool's rpd -- this
    # one exists to stop one person eating the shared budget
    user_rpd: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # wrap answers in <tg-spoiler> by default; groups may override, see
    # TeleGroup.lore_spoiler
    spoiler_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # set when RPD exhaustion disabled /ask, cleared on the daily reset so the
    # scheduler only re-enables a command that quota (not an admin) turned off
    rpd_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rpd_disabled_on: Mapped[str] = mapped_column(String, nullable=True)
