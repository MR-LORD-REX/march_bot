from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from shared.redis import redis_connector


class HandoffError(ValueError):
    pass


@dataclass(frozen=True)
class Handoff:
    token: str
    telegram_id: int
    chat_id: int
    message_id: int
    uid: int
    slot: int
    claimed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _key(token: str) -> str:
    return f"webapp:handoff:{token}"


def _new_token() -> str:
    # Telegram Mini App start_param is underscore-delimited in the deployed
    # client. Keep the token free of underscores so it can round-trip intact.
    return secrets.token_hex(24)


def _legacy_key(telegram_id: int, uid: int, slot: int, chat_id: int, message_id: int) -> str:
    return f"webapp:handoff-ref:{telegram_id}:{uid}:{slot}:{chat_id}:{message_id}"


def _client():
    try:
        return redis_connector.get_client()
    except RuntimeError as exc:
        raise HandoffError("redis not connected") from exc


async def _record_issue(handoff: Handoff, ttl: int) -> None:
    """Best-effort durable audit of a handoff; Redis remains authoritative."""
    try:
        from DB.asyncsessions import session_factory
        from DB.models.web_handoff import WebHandoff

        async with session_factory() as session:
            session.add(
                WebHandoff(
                    token=handoff.token,
                    telegram_id=handoff.telegram_id,
                    chat_id=handoff.chat_id,
                    message_id=handoff.message_id,
                    uid=handoff.uid,
                    slot=handoff.slot,
                    expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
                )
            )
            await session.commit()
    except Exception:
        return


async def _record_claim(token: str, telegram_id: int) -> None:
    try:
        from DB.asyncsessions import session_factory
        from DB.models.web_handoff import WebHandoff

        async with session_factory() as session:
            result = await session.execute(
                select(WebHandoff).where(
                    WebHandoff.token == token,
                    WebHandoff.telegram_id == telegram_id,
                    WebHandoff.claimed_at.is_(None),
                )
            )
            record = result.scalar_one_or_none()
            if record:
                record.claimed_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception:
        return


async def create_handoff(
    telegram_id: int,
    chat_id: int,
    message_id: int,
    uid: int,
    slot: int,
    ttl: int = 900,
) -> Handoff:
    """Create the server-side record that owns the editable origin message.

    The Mini App receives only a reference; it cannot choose chat_id or
    message_id during submission.
    """
    handoff = Handoff(
        token=_new_token(),
        telegram_id=telegram_id,
        chat_id=chat_id,
        message_id=message_id,
        uid=uid,
        slot=slot,
    )
    await save_handoff(handoff, ttl)
    await _record_issue(handoff, ttl)
    return handoff


async def save_handoff(handoff: Handoff, ttl: int = 900) -> None:
    payload = json.dumps(handoff.as_dict())
    await _client().set(_key(handoff.token), payload, ex=ttl)
    # The deployed Mini App submits the old uid/slot/chat/message tuple. Store a
    # secondary lookup so the server can recover the trusted origin instead of
    # accepting client-supplied destination ids.
    await _client().set(
        _legacy_key(
            handoff.telegram_id,
            handoff.uid,
            handoff.slot,
            handoff.chat_id,
            handoff.message_id,
        ),
        handoff.token,
        ex=ttl,
    )


async def get_handoff(token: str) -> Handoff:
    if not token:
        raise HandoffError("missing handoff")
    raw = await _client().get(_key(token))
    if not raw:
        raise HandoffError("handoff not found or expired")
    try:
        return Handoff(**json.loads(raw))
    except Exception as exc:
        raise HandoffError("invalid handoff") from exc


async def claim_handoff(token: str, telegram_id: int) -> Handoff:
    handoff = await get_handoff(token)
    if handoff.telegram_id != telegram_id:
        raise HandoffError("handoff belongs to another user")
    if not handoff.claimed:
        handoff = Handoff(**{**handoff.as_dict(), "claimed": True})
        await save_handoff(handoff)
        await _record_claim(token, telegram_id)
    return handoff


async def legacy_handoff(
    telegram_id: int,
    uid: int,
    slot: int,
    chat_id: int,
    message_id: int,
    ttl: int = 900,
) -> Handoff:
    """Resolve the already-deployed Mini App payload to a trusted handoff.

    The signed Telegram user is authoritative. The legacy tuple is only a
    lookup key for a handoff the bot issued earlier; it must never create a
    new destination from client input.
    """
    raw_token = await _client().get(
        _legacy_key(telegram_id, uid, slot, chat_id, message_id)
    )
    if not raw_token:
        raise HandoffError("handoff not found or expired")
    handoff = await get_handoff(raw_token)
    if handoff.telegram_id != telegram_id:
        raise HandoffError("handoff belongs to another user")
    if handoff.uid != uid or handoff.slot != slot:
        raise HandoffError("handoff does not match this card")
    if handoff.chat_id != chat_id or handoff.message_id != message_id:
        raise HandoffError("handoff destination mismatch")
    return handoff