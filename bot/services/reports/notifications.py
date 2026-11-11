from __future__ import annotations

import logging

from aiogram import Bot

from shared.config.settings import ADMIN_GC_ID

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, text: str) -> bool:
    """Best-effort admin notification that never blocks a user flow."""
    try:
        await bot.send_message(ADMIN_GC_ID, text)
        return True
    except Exception:
        logger.exception("failed to notify admins")
        return False