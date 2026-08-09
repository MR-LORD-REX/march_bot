"""Redis primitives for the lore chatbot: per-user conversation memory, the
reply-addressability map, and the atomic quota counters.

Policy lives in quota.py -- this module only owns key layout and the scripts
that have to run atomically.
"""

from typing import Any
import json
import logging

from bot.redis_store import redis_connector

logger = logging.getLogger(__name__)

HIST_KEY = "lore:hist:{user_id}"
REPLY_KEY = "lore:reply:{chat_id}:{msg_id}"
RPM_KEY = "lore:rpm:{api_name}:{model_name}"
RPD_KEY = "lore:rpd:{api_name}:{model_name}"
# The Pacific day is in the key, not just the TTL: a counter that outlives its
# TTL by a clock skew or a Redis restart then reads as a fresh day instead of
# silently carrying yesterday's total into today.
USER_RPD_KEY = "lore:urpd:{day}:{user_id}"

# Reserve one slot only if BOTH windows have room, and stamp the TTLs on the
# transition from 0 -> 1. Done in Lua because a GET-then-INCR from Python lets
# concurrent /ask calls read the same value and overshoot the cap -- with 15
# rpm and a shared pool that is a 429 waiting to happen.
_ACQUIRE_LUA = """
local rpd_used = tonumber(redis.call('GET', KEYS[2]) or '0')
if rpd_used >= tonumber(ARGV[2]) then
    return {-1, rpd_used}
end
local rpm_used = tonumber(redis.call('GET', KEYS[1]) or '0')
if rpm_used >= tonumber(ARGV[1]) then
    return {-2, rpm_used}
end
local m = redis.call('INCR', KEYS[1])
if m == 1 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
local d = redis.call('INCR', KEYS[2])
if d == 1 then redis.call('EXPIRE', KEYS[2], ARGV[4]) end
return {1, m, d}
"""

# Hand a slot back when the call never reached the model. Never drops below 0,
# and never resurrects a key that has already expired (a stale DECR would let
# the next window start negative and silently overspend).
_REFUND_LUA = """
for i = 1, 2 do
    if redis.call('EXISTS', KEYS[i]) == 1 then
        local v = tonumber(redis.call('GET', KEYS[i]) or '0')
        if v > 0 then redis.call('DECR', KEYS[i]) end
    end
end
return 1
"""

# Per-user daily allowance. Same shape as the pool acquire and for the same
# reason: two messages from one person must not both read "49 used" and pass.
_USER_ACQUIRE_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used >= tonumber(ARGV[1]) then
    return {0, used}
end
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
return {1, n}
"""

# Google said 429 -- believe it over our counter and burn the bucket for this
# window, so the rotator stops picking it instead of retrying into the wall.
_SATURATE_LUA = """
redis.call('SET', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

ACQUIRED = 1
RPD_EXHAUSTED = -1
RPM_EXHAUSTED = -2


class ChatRedis:
    """Thin wrapper over the shared Redis client.

    The client is resolved per call rather than cached in __init__, because
    this object is built at import time and redis_connector.connect() only
    runs on startup.
    """

    def __init__(self) -> None:
        self._acquire = None
        self._refund = None
        self._saturate = None
        self._user_acquire = None

    @property
    def client(self):
        return redis_connector.get_client()

    def _scripts(self):
        if self._acquire is None:
            c = self.client
            self._acquire = c.register_script(_ACQUIRE_LUA)
            self._refund = c.register_script(_REFUND_LUA)
            self._saturate = c.register_script(_SATURATE_LUA)
            self._user_acquire = c.register_script(_USER_ACQUIRE_LUA)
        return self._acquire, self._refund, self._saturate, self._user_acquire

    # ------------------------------------------------------------------
    # conversation memory
    # ------------------------------------------------------------------

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """Oldest-first list of {"q", "a"} turns. Never raises -- losing
        history should cost context, not the answer."""
        try:
            raw = await self.client.lrange(HIST_KEY.format(user_id=user_id), 0, -1)
        except Exception as e:
            logger.error(f"redis get_history failed for {user_id}: {e}")
            return []

        turns: list[dict[str, str]] = []
        for item in raw:
            try:
                turns.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        return turns

    async def append_turn(
        self,
        user_id: int,
        question: str,
        answer: str,
        max_turns: int,
        ttl: int,
    ) -> None:
        key = HIST_KEY.format(user_id=user_id)
        payload = json.dumps({"q": question, "a": answer})
        try:
            pipe = self.client.pipeline()
            pipe.rpush(key, payload)
            # trim on every write so a lowered max_turns takes effect at once
            pipe.ltrim(key, -max_turns, -1)
            pipe.expire(key, ttl)
            await pipe.execute()
        except Exception as e:
            logger.error(f"redis append_turn failed for {user_id}: {e}")

    async def clear_history(self, user_id: int) -> bool:
        try:
            return bool(await self.client.delete(HIST_KEY.format(user_id=user_id)))
        except Exception as e:
            logger.error(f"redis clear_history failed for {user_id}: {e}")
            return False

    async def history_len(self, user_id: int) -> int:
        try:
            return int(await self.client.llen(HIST_KEY.format(user_id=user_id)))
        except Exception as e:
            logger.error(f"redis history_len failed for {user_id}: {e}")
            return 0

    # ------------------------------------------------------------------
    # reply addressability
    # ------------------------------------------------------------------

    async def remember_answer(
        self,
        chat_id: int,
        msg_id: int,
        owner_id: int,
        ttl: int,
    ) -> None:
        """Mark a bot message as replyable, and record who it was answering.
        Expiry is the feature, not cleanup: past the TTL a reply is just a
        message again."""
        try:
            await self.client.set(
                REPLY_KEY.format(chat_id=chat_id, msg_id=msg_id),
                json.dumps({"owner": owner_id}),
                ex=ttl,
            )
        except Exception as e:
            logger.error(f"redis remember_answer failed for {chat_id}/{msg_id}: {e}")

    async def get_answer_owner(self, chat_id: int, msg_id: int) -> int | None:
        try:
            raw = await self.client.get(
                REPLY_KEY.format(chat_id=chat_id, msg_id=msg_id)
            )
        except Exception as e:
            logger.error(f"redis get_answer_owner failed for {chat_id}/{msg_id}: {e}")
            return None
        if not raw:
            return None
        try:
            return int(json.loads(raw)["owner"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # quota counters
    # ------------------------------------------------------------------

    async def try_acquire(
        self,
        api_name: str,
        model_name: str,
        rpm: int,
        rpd: int,
        day_ttl: int,
        minute_window: int = 60,
    ) -> tuple[int, dict[str, int]]:
        """Reserve one request on a (key, model) bucket.

        Returns (status, info) where status is ACQUIRED / RPM_EXHAUSTED /
        RPD_EXHAUSTED. A Redis failure returns ACQUIRED: the model's own 429
        is a correct-but-slower backstop, and refusing to answer because the
        bookkeeping is down is the worse trade.
        """
        acquire, _, _, _ = self._scripts()
        try:
            res = await acquire(
                keys=[
                    RPM_KEY.format(api_name=api_name, model_name=model_name),
                    RPD_KEY.format(api_name=api_name, model_name=model_name),
                ],
                args=[rpm, rpd, minute_window, day_ttl],
            )
        except Exception as e:
            logger.error(f"redis try_acquire failed for {api_name}/{model_name}: {e}")
            return ACQUIRED, {"degraded": 1}

        status = int(res[0])
        if status == ACQUIRED:
            return status, {"rpm_used": int(res[1]), "rpd_used": int(res[2])}
        return status, {"used": int(res[1])}

    async def refund(self, api_name: str, model_name: str) -> None:
        _, refund, _, _ = self._scripts()
        try:
            await refund(keys=[
                RPM_KEY.format(api_name=api_name, model_name=model_name),
                RPD_KEY.format(api_name=api_name, model_name=model_name),
            ])
        except Exception as e:
            logger.error(f"redis refund failed for {api_name}/{model_name}: {e}")

    async def saturate(
        self,
        api_name: str,
        model_name: str,
        scope: str,
        limit: int,
        ttl: int,
    ) -> None:
        """Force a bucket to its cap for the rest of the window ('minute') or
        the day ('day')."""
        _, _, saturate, _ = self._scripts()
        key = (
            RPM_KEY if scope == "minute" else RPD_KEY
        ).format(api_name=api_name, model_name=model_name)
        try:
            await saturate(keys=[key], args=[limit, ttl])
        except Exception as e:
            logger.error(f"redis saturate failed for {api_name}/{model_name}: {e}")

    async def usage(self, buckets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Current rpm/rpd usage for each bucket, for the admin readout."""
        if not buckets:
            return []
        try:
            pipe = self.client.pipeline()
            for b in buckets:
                pipe.get(RPM_KEY.format(
                    api_name=b["api_name"], model_name=b["model_name"]))
                pipe.get(RPD_KEY.format(
                    api_name=b["api_name"], model_name=b["model_name"]))
            raw = await pipe.execute()
        except Exception as e:
            logger.error(f"redis usage failed: {e}")
            raw = [None] * (len(buckets) * 2)

        out = []
        for i, b in enumerate(buckets):
            out.append({
                "api_name": b["api_name"],
                "model_name": b["model_name"],
                "rpm_used": int(raw[i * 2] or 0),
                "rpm": b["rpm"],
                "rpd_used": int(raw[i * 2 + 1] or 0),
                "rpd": b["rpd"],
            })
        return out

    async def reset_counters(self, buckets: list[dict[str, Any]]) -> int:
        """Drop every counter -- used by the daily reset and by /lore_reset."""
        if not buckets:
            return 0
        keys = []
        for b in buckets:
            keys.append(RPM_KEY.format(
                api_name=b["api_name"], model_name=b["model_name"]))
            keys.append(RPD_KEY.format(
                api_name=b["api_name"], model_name=b["model_name"]))
        try:
            return int(await self.client.delete(*keys))
        except Exception as e:
            logger.error(f"redis reset_counters failed: {e}")
            return 0

    # ------------------------------------------------------------------
    # per-user daily allowance
    # ------------------------------------------------------------------

    async def user_try_acquire(
        self, user_id: int, day: str, cap: int, day_ttl: int
    ) -> tuple[bool, int]:
        """Reserve one request on this user's daily allowance.

        Returns (acquired, used) where acquired is True if the user had room.
        The day string is typically 'YYYY-MM-DD' Pacific, which is what the key
        stores -- a day-skew resilient alternative to a TTL-only counter.
        """
        *_, user_acquire = self._scripts()
        try:
            res = await user_acquire(
                keys=[USER_RPD_KEY.format(day=day, user_id=user_id)],
                args=[cap, day_ttl],
            )
            return bool(res[0]), int(res[1])
        except Exception as e:
            logger.error(f"redis user_try_acquire failed for {user_id}: {e}")
            return True, 0

    async def user_usage(self, user_id: int, day: str) -> int:
        """How many requests this user has made today. The day must match the
        counter's embedded day or it reads as 0 -- that is what makes a stale
        key (one that outlived its TTL) read as a fresh day."""
        try:
            raw = await self.client.get(USER_RPD_KEY.format(day=day, user_id=user_id))
            return int(raw) if raw else 0
        except Exception as e:
            logger.error(f"redis user_usage failed for {user_id}: {e}")
            return 0


chat_redis = ChatRedis()
