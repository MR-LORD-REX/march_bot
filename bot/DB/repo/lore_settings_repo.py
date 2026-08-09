from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.repo.base import BaseRepo
from bot.DB.models.lore_settings import LoreSettings

logger = logging.getLogger(__name__)

# fields /lore_config may set, with their accepted range
TUNABLES: dict[str, tuple[int, int]] = {
    "max_turns": (1, 50),
    "history_ttl": (300, 604800),
    "reply_ttl": (60, 3600),
    "handoff_turns": (1, 10),
    "rpm_wait": (0, 120),
    "max_question_len": (100, 4000),
    "user_rpd": (1, 2000),
}


class LoreSettingsRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(LoreSettings, session)
        self.model: type[LoreSettings] = LoreSettings

    async def get(self) -> LoreSettings:
        """Fetch the single settings row, creating it with defaults on first
        call so no startup ordering is required."""
        query = select(self.model).where(self.model.id == 1)
        result = await self.session.execute(query)
        row = result.scalar_one_or_none()
        if not row:
            row = LoreSettings(id=1)
            await self.add(row)
            await self.session.commit()
        return row

    async def update_field(self, field: str, value: int) -> tuple[bool, str]:
        if field not in TUNABLES:
            return False, f"unknown setting '{field}'"
        low, high = TUNABLES[field]
        if not low <= value <= high:
            return False, f"{field} must be between {low} and {high}"

        row = await self.get()
        setattr(row, field, value)
        await self.update(row)
        return True, f"{field} set to {value}"

    async def set_spoiler_default(self, spoiler: bool) -> None:
        """Bot-wide spoiler default. Groups that set their own override are
        unaffected -- see TeleGroup.lore_spoiler."""
        row = await self.get()
        row.spoiler_default = spoiler
        await self.update(row)

    async def set_rpd_disabled(self, disabled: bool, day: str | None = None) -> None:
        row = await self.get()
        row.rpd_disabled = disabled
        row.rpd_disabled_on = day
        await self.update(row)
