from __future__ import annotations

from enum import IntEnum
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import OWNER_TELE_ID
from DB.repo.admin_repo import AdminRepo

Authority = Literal["basic", "moderator", "admin", "owner"]


class AuthorityLevel(IntEnum):
    none = 0
    basic = 1
    moderator = 2
    admin = 3
    owner = 4


_AUTHORITY_LEVELS = {
    "basic": AuthorityLevel.basic,
    "moderator": AuthorityLevel.moderator,
    "admin": AuthorityLevel.admin,
    "owner": AuthorityLevel.owner,
}


async def get_authority(session: AsyncSession, telegram_id: int) -> Authority | None:
    """Resolve the effective authority for a Telegram user.

    OWNER_TELE_ID remains an emergency override so a lost admin row cannot
    lock the bot owner out. All other checks come from the admins table.
    """
    if telegram_id == OWNER_TELE_ID:
        return "owner"

    admin = await AdminRepo(session).get_admin(telegram_id)
    return admin.authority if admin else None


def level_of(authority: str | None) -> AuthorityLevel:
    return _AUTHORITY_LEVELS.get(authority or "", AuthorityLevel.none)


def has_authority(authority: str | None, minimum: Authority) -> bool:
    return level_of(authority) >= level_of(minimum)


async def require_authority(
    session: AsyncSession,
    telegram_id: int,
    minimum: Authority,
) -> bool:
    return has_authority(await get_authority(session, telegram_id), minimum)