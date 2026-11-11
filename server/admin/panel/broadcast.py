"""Throttled broadcast delivery.

HTTP creates a queued row and returns; this module owns the actual Telegram
calls so a slow or rate-limited audience never ties up a panel request. Only
one worker runs per process; the database row is the audit trail.
"""

from __future__ import annotations

import asyncio
import logging
from html.parser import HTMLParser

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from sqlalchemy import select

from DB.asyncsessions import session_factory
from DB.models.broadcast import Broadcast
from DB.models.tele_group import TeleGroup
from DB.models.users import Users
from DB.repo.broadcast_repo import BroadcastRepo

logger = logging.getLogger(__name__)

AUDIENCES = {"groups", "users", "all"}

_worker_task: asyncio.Task | None = None
_queue: asyncio.Queue[tuple[int, Bot]] | None = None


def _get_queue() -> asyncio.Queue[tuple[int, Bot]]:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


def validate_html(body: str) -> str | None:
    """Return a Telegram HTML parse error without sending anything.

    Telegram rejects the whole message on a malformed tag, so catching this
    at queue time gives the operator a useful error instead of a broadcast
    that fails once per recipient.
    """
    checker = _HtmlProbe(body)
    try:
        checker.feed(body)
        checker.close()
        if checker.stack:
            raise ValueError(f"unclosed tag <{checker.stack[-1]}>")
    except Exception as exc:
        return str(exc)
    return None


class _HtmlProbe(HTMLParser):
    _ALLOWED = {
        "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
        "a", "code", "pre", "blockquote", "tg-spoiler", "tg-emoji", "br",
    }
    _VOID = {"br"}

    def __init__(self, body: str) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag not in self._ALLOWED:
            raise ValueError(f"unsupported tag <{tag}>")
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f"unexpected closing tag </{tag}>")
        self.stack.pop()


async def enqueue(broadcast_id: int, bot: Bot) -> None:
    await _get_queue().put((broadcast_id, bot))
    _ensure_worker()


def _ensure_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_worker(), name="broadcast-worker")


async def _targets(broadcast: Broadcast) -> list[int]:
    async with session_factory() as session:
        if broadcast.audience == "groups":
            rows = (await session.execute(select(TeleGroup.group_id))).scalars().all()
        elif broadcast.audience == "users":
            rows = (await session.execute(select(Users.telegram_id))).scalars().all()
        else:
            groups = (await session.execute(select(TeleGroup.group_id))).scalars().all()
            users = (await session.execute(select(Users.telegram_id))).scalars().all()
            rows = list(users) + list(groups)
    return list(dict.fromkeys(int(row) for row in rows if row is not None))


async def _send_one(bot: Bot, chat_id: int, body: str, parse_mode: str | None) -> bool:
    for attempt in range(2):
        try:
            await bot.send_message(chat_id, body, parse_mode=parse_mode)
            return True
        except TelegramRetryAfter as exc:
            if attempt == 1:
                raise
            await asyncio.sleep(float(exc.retry_after) + 0.5)
        except Exception as exc:
            logger.warning("broadcast delivery to %s failed: %s", chat_id, exc)
            return False
    return False


async def _worker() -> None:
    queue = _get_queue()
    while True:
        broadcast_id, bot = await queue.get()
        try:
            async with session_factory() as session:
                repo = BroadcastRepo(session)
                broadcast = await repo.get(broadcast_id)
                if not broadcast or broadcast.status not in {"queued", "running"}:
                    continue
                targets = await _targets(broadcast)
                await repo.claim(broadcast, len(targets))
                await session.commit()

            sent = 0
            failed = 0
            last_error: str | None = None
            for index, chat_id in enumerate(targets):
                if index:
                    await asyncio.sleep(0.08)
                try:
                    if await _send_one(bot, chat_id, broadcast.body, broadcast.parse_mode):
                        sent += 1
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    last_error = str(exc)[:500]
                    logger.warning("broadcast %s target %s failed: %s", broadcast_id, chat_id, exc)

            async with session_factory() as session:
                repo = BroadcastRepo(session)
                row = await repo.get(broadcast_id)
                if row:
                    await repo.record_result(row, sent, failed, last_error)
                    await session.commit()
        except Exception:
            logger.exception("broadcast worker failed for %s", broadcast_id)
            async with session_factory() as session:
                repo = BroadcastRepo(session)
                row = await repo.get(broadcast_id)
                if row:
                    await repo.fail(row, "broadcast worker crashed")
                    await session.commit()
        finally:
            queue.task_done()


async def stop_worker() -> None:
    global _worker_task
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None