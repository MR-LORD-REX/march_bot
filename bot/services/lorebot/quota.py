"""Quota policy for the Gemini key pool.

Each (api key, model) pair is an independent bucket with its own rpm/rpd.
Adding a key with /add_api adds one bucket per model, so quota scales with
keys. A request takes the first bucket with room, scanning round-robin so
load spreads instead of always burning key #1 first.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import logging

from bot.services.lorebot.chat_redis import (
    chat_redis,
    ACQUIRED,
    RPD_EXHAUSTED,
)

logger = logging.getLogger(__name__)

try:  # Windows has no system tz database; tzdata provides it
    from zoneinfo import ZoneInfo

    PACIFIC = ZoneInfo("America/Los_Angeles")
except Exception:  # pragma: no cover - falls back to hand-rolled US rules
    PACIFIC = None
    logger.warning(
        "zoneinfo has no America/Los_Angeles (install tzdata); "
        "using built-in US Pacific DST rules"
    )

POLL_INTERVAL = 1.5


def _us_pacific_offset(utc_dt: datetime) -> timedelta:
    """US Pacific offset without a tz database: DST runs from the 2nd Sunday
    in March (02:00 PST = 10:00 UTC) to the 1st Sunday in November
    (02:00 PDT = 09:00 UTC)."""
    year = utc_dt.year
    mar = datetime(year, 3, 1, tzinfo=timezone.utc)
    start = (mar + timedelta(days=(6 - mar.weekday()) % 7 + 7)).replace(hour=10)
    nov = datetime(year, 11, 1, tzinfo=timezone.utc)
    end = (nov + timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=9)
    return timedelta(hours=-7) if start <= utc_dt < end else timedelta(hours=-8)


def pacific_now() -> datetime:
    """Now, in the timezone Google's free-tier daily counter resets in."""
    if PACIFIC is not None:
        return datetime.now(PACIFIC)
    utc = datetime.now(timezone.utc)
    return utc.astimezone(timezone(_us_pacific_offset(utc)))


def pacific_day() -> str:
    return pacific_now().strftime("%Y-%m-%d")


def seconds_to_pacific_midnight() -> int:
    """Seconds until the daily quota refills. Subtracting two aware datetimes
    gets the DST-shortened/lengthened day right on its own."""
    now = pacific_now()
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(60, int((tomorrow - now).total_seconds()))


@dataclass
class Slot:
    api_name: str
    api_key: str
    model_name: str
    rpm: int
    rpd: int

    @property
    def label(self) -> str:
        return f"{self.api_name}/{self.model_name}"


class QuotaManager:
    def __init__(self) -> None:
        self._slots: list[Slot] = []
        self._cursor = 0

    @property
    def slots(self) -> list[Slot]:
        return self._slots

    @property
    def total_rpm(self) -> int:
        return sum(s.rpm for s in self._slots)

    @property
    def total_rpd(self) -> int:
        return sum(s.rpd for s in self._slots)

    def as_dicts(self) -> list[dict]:
        return [
            {
                "api_name": s.api_name,
                "model_name": s.model_name,
                "rpm": s.rpm,
                "rpd": s.rpd,
            }
            for s in self._slots
        ]

    async def refresh(self) -> int:
        """Reload the pool from the DB. Called on startup and after any key
        change so /add_api takes effect without a restart."""
        from bot.DB.asyncsessions import session_factory
        from bot.DB.repo.ai_api_repo import AiApiRepo

        try:
            async with session_factory() as session:
                buckets = await AiApiRepo(session).get_active_buckets()
        except Exception as e:
            logger.error(f"failed to load api key pool: {e}")
            return len(self._slots)

        self._slots = [Slot(**b) for b in buckets]
        if self._cursor >= len(self._slots):
            self._cursor = 0
        logger.info(
            f"lore quota pool: {len(self._slots)} buckets, "
            f"{self.total_rpm} rpm / {self.total_rpd} rpd"
        )
        return len(self._slots)

    async def acquire(self, wait: int = 0) -> tuple[Slot | None, str]:
        """Reserve capacity for one API call.

        Returns (slot, status): "ok", "rpm" (every bucket is at its per-minute
        cap and the wait ran out), "rpd" (the day is spent -- /ask should be
        disabled), or "empty" (no keys configured).
        """
        if not self._slots:
            return None, "empty"

        day_ttl = seconds_to_pacific_midnight()
        deadline = asyncio.get_running_loop().time() + max(0, wait)

        while True:
            n = len(self._slots)
            rpd_full = 0

            for offset in range(n):
                slot = self._slots[(self._cursor + offset) % n]
                status, _ = await chat_redis.try_acquire(
                    api_name=slot.api_name,
                    model_name=slot.model_name,
                    rpm=slot.rpm,
                    rpd=slot.rpd,
                    day_ttl=day_ttl,
                )
                if status == ACQUIRED:
                    self._cursor = (self._cursor + offset + 1) % n
                    return slot, "ok"
                if status == RPD_EXHAUSTED:
                    rpd_full += 1

            if rpd_full >= n:
                return None, "rpd"

            # Every bucket is rpm-capped. Windows are 60s, so a short poll
            # usually clears; the caller's budget decides how long to try.
            if asyncio.get_running_loop().time() + POLL_INTERVAL > deadline:
                return None, "rpm"
            await asyncio.sleep(POLL_INTERVAL)

    async def release(self, slot: Slot) -> None:
        """Return a reservation that never reached the model."""
        await chat_redis.refund(slot.api_name, slot.model_name)

    async def mark_rate_limited(self, slot: Slot, daily: bool = False) -> None:
        """Google returned 429 for this bucket. Trust it over our counter."""
        if daily:
            await chat_redis.saturate(
                slot.api_name, slot.model_name,
                scope="day", limit=slot.rpd, ttl=seconds_to_pacific_midnight(),
            )
        else:
            await chat_redis.saturate(
                slot.api_name, slot.model_name,
                scope="minute", limit=slot.rpm, ttl=60,
            )
        logger.warning(
            f"bucket {slot.label} saturated by upstream 429 "
            f"({'daily' if daily else 'per-minute'})"
        )

    async def charge(self, slot: Slot, extra: int) -> None:
        """Bill extra API calls the SDK made behind our back (automatic
        function calling loops back to the model once per tool round)."""
        if extra <= 0:
            return
        for _ in range(extra):
            await chat_redis.try_acquire(
                api_name=slot.api_name,
                model_name=slot.model_name,
                rpm=slot.rpm,
                rpd=slot.rpd,
                day_ttl=seconds_to_pacific_midnight(),
            )

    async def usage(self) -> list[dict]:
        return await chat_redis.usage(self.as_dicts())

    async def is_daily_exhausted(self) -> bool:
        rows = await self.usage()
        if not rows:
            return False
        return all(r["rpd_used"] >= r["rpd"] for r in rows)

    async def reset(self) -> int:
        return await chat_redis.reset_counters(self.as_dicts())
