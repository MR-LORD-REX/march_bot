from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select

from DB.asyncsessions import session_factory
from DB.models.reports import WebSession
from DB.repo.user_repo import UserRepo
from shared.auth.authority import Authority, get_authority, has_authority

PANEL_COOKIE = "hsr_panel"
SESSION_TTL_SECONDS = 8 * 60 * 60
_LOGIN_TTL_SECONDS = 10 * 60


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _login_key(token: str) -> str:
    return f"webapp:panel-login:{token}"


async def create_login_token(telegram_id: int, ttl: int = _LOGIN_TTL_SECONDS) -> str:
    """Issue a one-time panel login token through the bot.

    The bot chat is the trusted channel. The token is stored in Redis only as
    a short-lived bearer reference; the browser exchanges it once for a
    server-side session cookie.
    """
    from shared.redis import redis_connector

    token = secrets.token_urlsafe(32)
    await redis_connector.get_client().set(_login_key(token), str(telegram_id), ex=ttl)
    return token


async def consume_login_token(token: str) -> int | None:
    from shared.redis import redis_connector

    if not token:
        return None
    raw = await redis_connector.get_client().getdel(_login_key(token))
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def create_session(telegram_id: int, ttl: int = SESSION_TTL_SECONDS) -> str:
    token = secrets.token_urlsafe(32)
    async with session_factory() as session:
        session.add(
            WebSession(
                token_hash=_hash(token),
                telegram_id=telegram_id,
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
            )
        )
        await session.commit()
    return token


async def _find_session(session, token: str) -> WebSession | None:
    result = await session.execute(
        select(WebSession).where(WebSession.token_hash == _hash(token))
    )
    return result.scalar_one_or_none()


async def resolve_session(token: str) -> int | None:
    if not token:
        return None
    async with session_factory() as session:
        row = await _find_session(session, token)
        if not row:
            return None
        now = datetime.now(timezone.utc)
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if row.revoked_at is not None or expires <= now:
            return None
        return row.telegram_id


async def revoke_session(token: str) -> None:
    if not token:
        return
    async with session_factory() as session:
        row = await _find_session(session, token)
        if row and row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            await session.commit()


async def get_panel_user(request: Request) -> dict | None:
    token = request.cookies.get(PANEL_COOKIE)
    telegram_id = await resolve_session(token or "")
    if not telegram_id:
        return None

    async with session_factory() as session:
        user = await UserRepo(session).get_by_tele_id(telegram_id)
        authority = await get_authority(session, telegram_id)
        if not authority:
            return None
        return {
            "telegram_id": telegram_id,
            "authority": authority,
            "username": user.username if user else None,
            "display_name": user.display_name if user else None,
        }


async def require_panel_user(request: Request, minimum: Authority = "moderator") -> dict | None:
    user = await get_panel_user(request)
    if not user:
        return None
    if not has_authority(user["authority"], minimum):
        return None
    return user