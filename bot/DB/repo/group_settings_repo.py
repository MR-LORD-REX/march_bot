from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.models.group_settings import GroupCommandSettings

logger = logging.getLogger(__name__)

# Commands a group admin may switch off. /group_settings itself is deliberately
# absent -- a group must never be able to lock its own admins out of the panel.
GROUP_TOGGLEABLE: dict[str, str] = {
    "ask": "Lore chatbot",
}


class GroupCommandSettingsRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def is_enabled(self, group_id: int, cmd: str) -> bool | None:
        """True/False if the group chose, None if it never did.

        None is not the same as True: it means "inherit", so a later change to
        the bot-wide default still reaches this group.
        """
        row = await self.session.scalar(
            select(GroupCommandSettings).where(
                GroupCommandSettings.group_id == group_id,
                GroupCommandSettings.cmd == cmd,
            )
        )
        return None if row is None else bool(row.enabled)

    async def get_all(self, group_id: int) -> dict[str, bool]:
        rows = (await self.session.scalars(
            select(GroupCommandSettings).where(
                GroupCommandSettings.group_id == group_id
            )
        )).all()
        return {r.cmd: bool(r.enabled) for r in rows}

    async def set_enabled(self, group_id: int, cmd: str, enabled: bool) -> bool:
        if cmd not in GROUP_TOGGLEABLE:
            logger.warning(f"refusing to toggle non-groupable command: {cmd}")
            return False

        row = await self.session.scalar(
            select(GroupCommandSettings).where(
                GroupCommandSettings.group_id == group_id,
                GroupCommandSettings.cmd == cmd,
            )
        )
        if row is None:
            self.session.add(GroupCommandSettings(
                group_id=group_id, cmd=cmd, enabled=enabled,
            ))
        else:
            row.enabled = enabled
        await self.session.flush()
        return True
