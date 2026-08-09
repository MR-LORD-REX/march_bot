"""Spoiler wrapping for lore answers.

Answers are wrapped in <tg-spoiler> by default so a lore reply in a group
does not spoil the story for people scrolling past. The bot owner sets the
global default; group admins may override it for their own group.
"""

import logging
import re

logger = logging.getLogger(__name__)

SPOILER_OPEN = "<tg-spoiler>"
SPOILER_CLOSE = "</tg-spoiler>"

# Telegram rejects a spoiler nested inside a spoiler, and the model is told it
# may use tg-spoiler itself -- so strip any it produced before wrapping.
_SPOILER_TAG = re.compile(r"</?tg-spoiler>", re.IGNORECASE)


def strip_spoilers(text: str) -> str:
    return _SPOILER_TAG.sub("", text)


def apply_spoiler(text: str, enabled: bool) -> str:
    """Wrap a whole answer in a spoiler, or leave it plain.

    Applied per chunk by the caller: a spoiler tag cannot span two Telegram
    messages, so each chunk has to open and close its own.
    """
    if not enabled:
        return text
    inner = strip_spoilers(text).strip()
    if not inner:
        return text
    return f"{SPOILER_OPEN}{inner}{SPOILER_CLOSE}"


async def spoiler_enabled(chat_id: int, is_group: bool) -> bool:
    """Resolve the spoiler setting for a chat.

    Group override wins when set; otherwise the bot-wide default applies. DMs
    always use the bot-wide default -- there is nobody there to spoil for, but
    honouring the owner's choice keeps one switch meaningful everywhere.
    """
    from bot.services.lorebot.runtime import settings

    if not is_group:
        return settings.spoiler_default

    try:
        from bot.DB.asyncsessions import session_factory
        from bot.DB.repo.tele_group_repo import TeleGroupRepo

        async with session_factory() as session:
            group = await TeleGroupRepo(session).get_group(chat_id)
            if group is not None and group.lore_spoiler is not None:
                return bool(group.lore_spoiler)
    except Exception as e:
        # A DB hiccup should not decide whether something is a spoiler; the
        # default is the safer of the two.
        logger.error(f"failed to read spoiler setting for {chat_id}: {e}")

    return settings.spoiler_default
