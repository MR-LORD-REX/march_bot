"""Process-wide lore chatbot state: the quota pool, the mirrored settings,
and the RPD kill-switch.

Mirrors the CommandsAvailability pattern -- the DB is the source of truth,
this is the copy handlers read on the hot path. Reload after any admin write.
"""

import logging

from bot.services.lorebot.chat import ChatBot
from bot.services.lorebot.quota import QuotaManager, pacific_day
from bot.DB.repo.lore_settings_repo import LoreSettingsRepo

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, int] = {
    "max_turns": 10,
    "history_ttl": 86400,
    "reply_ttl": 300,
    "handoff_turns": 3,
    "rpm_wait": 25,
    "max_question_len": 1000,
    "user_rpd": 50,
}


class LoreSettings:
    """In-memory mirror of the lore_settings row."""

    def __init__(self) -> None:
        self._values: dict[str, int] = dict(DEFAULTS)
        self.rpd_disabled: bool = False
        self.rpd_disabled_on: str | None = None
        self.spoiler_default: bool = True

    def __getitem__(self, key: str) -> int:
        return self._values.get(key, DEFAULTS.get(key, 0))

    def get(self, key: str) -> int:
        return self[key]

    def as_dict(self) -> dict[str, int]:
        return dict(self._values)

    def load(self, row) -> None:
        for key in DEFAULTS:
            value = getattr(row, key, None)
            # bools are ints in Python; guard so a Boolean column can never
            # land in the numeric tunables
            if isinstance(value, int) and not isinstance(value, bool):
                self._values[key] = value
        self.rpd_disabled = bool(getattr(row, "rpd_disabled", False))
        self.rpd_disabled_on = getattr(row, "rpd_disabled_on", None)
        self.spoiler_default = bool(getattr(row, "spoiler_default", True))


quota_manager = QuotaManager()
settings = LoreSettings()
chat_bot = ChatBot(quota=quota_manager)


async def take_user_slot(user_id: int) -> tuple[bool, int, int]:
    """Charge one question to a user's daily allowance.

    Returns (allowed, used, cap). Counted per question asked, not per API call:
    a single question may cost the pool two calls (rewrite + answer) and users
    should not have to reason about that.
    """
    from bot.services.lorebot.chat_redis import chat_redis
    from bot.services.lorebot.quota import seconds_to_pacific_midnight

    cap = settings["user_rpd"]
    ok, used = await chat_redis.user_try_acquire(
        user_id=user_id,
        day=pacific_day(),
        cap=cap,
        day_ttl=seconds_to_pacific_midnight(),
    )
    return ok, used, cap


async def user_usage(user_id: int) -> tuple[int, int]:
    """(used, cap) for this user today, for /ask_status."""
    from bot.services.lorebot.chat_redis import chat_redis

    used = await chat_redis.user_usage(user_id, pacific_day())
    return used, settings["user_rpd"]


async def reload_settings() -> None:
    from bot.DB.asyncsessions import session_factory

    try:
        async with session_factory() as session:
            row = await LoreSettingsRepo(session).get()
            settings.load(row)
    except Exception as e:
        logger.error(f"failed to load lore settings, keeping defaults: {e}")


async def reload_pool() -> int:
    """Re-read the key pool and drop cached genai clients so a removed or
    rotated key stops being used."""
    count = await quota_manager.refresh()
    chat_bot.drop_clients()
    return count


async def set_ask_enabled(enabled: bool, reason: str = "") -> None:
    """Flip /ask through the existing command-availability machinery so the
    CommandChecker middleware enforces it, and record whether quota (rather
    than an admin) was the one that turned it off."""
    from bot.DB.asyncsessions import session_factory
    from bot.DB.repo.cmd_meta_repo import CommandMetaRepo
    from bot.config.config import cmdavailability

    async with session_factory() as session:
        repo = CommandMetaRepo(session)
        if enabled:
            await repo.update_cmd("ask", True)
            meta = await repo.get_command_meta("ask")
            if meta:
                meta.reason = ""
                await repo.update(meta)
        else:
            await repo.disable_command("ask", reason)
        await session.commit()

        await LoreSettingsRepo(session).set_rpd_disabled(
            not enabled, None if enabled else pacific_day()
        )
        await session.commit()

        status = await repo.get_all_commands()

    cmdavailability.load(status)
    settings.rpd_disabled = not enabled
    settings.rpd_disabled_on = None if enabled else pacific_day()


async def on_rpd_exhausted() -> None:
    """Every bucket is out of daily quota: warn the admin group once and take
    /ask offline until the Pacific-midnight reset."""
    if settings.rpd_disabled:
        return

    reason = (
        "Daily Gemini quota exhausted on all API keys. "
        "Re-enables automatically at the next quota reset (midnight PT)."
    )
    await set_ask_enabled(False, reason)

    from bot.config.config import ADMIN_GC_ID
    from bot.core.main import bot

    rows = await quota_manager.usage()
    used = sum(r["rpd_used"] for r in rows)
    cap = sum(r["rpd"] for r in rows)
    try:
        await bot.send_message(
            ADMIN_GC_ID,
            "⚠️ <b>Lore chatbot: daily quota exhausted</b>\n\n"
            f"All {len(rows)} key/model buckets are at their RPD cap "
            f"({used}/{cap} requests).\n"
            "/ask has been disabled and will re-enable at the next reset "
            "(midnight America/Los_Angeles).\n\n"
            "Add capacity with /add_api, or re-enable early with "
            "<code>/lore_enable</code>.",
        )
    except Exception as e:
        logger.error(f"failed to send rpd warning to admin gc: {e}")


async def daily_quota_reset() -> None:
    """Scheduled at Pacific midnight: clear counters and lift a quota-imposed
    disable. An admin-imposed disable is left alone -- rpd_disabled tells the
    two apart."""
    cleared = await quota_manager.reset()
    logger.info(f"lore daily reset: cleared {cleared} counter keys")

    if not settings.rpd_disabled:
        return

    await set_ask_enabled(True)
    logger.info("lore daily reset: /ask re-enabled")

    from bot.config.config import ADMIN_GC_ID
    from bot.core.main import bot

    try:
        await bot.send_message(
            ADMIN_GC_ID,
            "✅ <b>Lore chatbot quota reset</b>\n\n"
            f"Daily counters cleared. /ask is enabled again "
            f"({quota_manager.total_rpd} requests available today).",
        )
    except Exception as e:
        logger.error(f"failed to send quota reset notice: {e}")
