from __future__ import annotations

import html
import logging
from typing import Any

from aiogram import Bot

from bot.config.config import ADMIN_GC_ID
from bot.DB.models.reports import Report
from bot.DB.repo.report_repo import ReportRepo
from bot.DB.repo.user_repo import UserRepo

logger = logging.getLogger(__name__)


def _user_line(user: Any) -> str:
    if not user:
        return "User: unknown"
    username = f"@{user.username}" if user.username else user.display_name or "unknown"
    return f"User: {html.escape(str(username))} ({user.telegram_id})"


def admin_text(report: Report, user: Any) -> str:
    return (
        f"Report #{report.id}\n"
        f"Type: {html.escape(str(report.report_type))}\n"
        f"UID: {report.uid or 'unknown'}\n"
        f"{_user_line(user)}\n"
        f"Origin chat: {report.origin_chat_id or 'unknown'}\n"
        f"Origin message: {report.origin_message_id or 'unknown'}\n\n"
        f"Reply with /r {report.id} <message> to answer the reporter."
    )


async def create_or_get_report(
    session,
    bot: Bot,
    *,
    reporter_id: int,
    report_type: str,
    uid: int,
    origin_chat_id: int | None,
    origin_message_id: int | None,
) -> tuple[Report, bool]:
    repo = ReportRepo(session)
    existing = await repo.get_open_for_origin(
        reporter_id, report_type, origin_chat_id, origin_message_id
    )
    if existing:
        return existing, False

    report = await repo.create(
        reporter_id=reporter_id,
        report_type=report_type,
        uid=uid,
        origin_chat_id=origin_chat_id,
        origin_message_id=origin_message_id,
    )
    return report, True


async def notify_report_created(
    session,
    bot: Bot,
    report: Report,
) -> None:
    repo = ReportRepo(session)
    user = await UserRepo(session).get_by_tele_id(report.reporter_id)
    try:
        message = await bot.send_message(ADMIN_GC_ID, admin_text(report, user))
        await repo.set_admin_message(report, message.chat.id, message.message_id)
        await repo.add_event(report.id, None, "admin_notified")
    except Exception:
        logger.exception("could not notify admins about report %s", report.id)
        await repo.add_event(report.id, None, "admin_notify_failed")


def _reply_text(report: Report, reporter: Any, body: str) -> str:
    name = "User"
    if reporter:
        name = reporter.display_name or (f"@{reporter.username}" if reporter.username else "User")
    escaped_name = html.escape(name)
    escaped_body = html.escape(body)
    return (
        f'<a href="tg://user?id={report.reporter_id}">{escaped_name}</a>\n'
        f"Reply to your report #{report.id}:\n{escaped_body}"
    )


async def deliver_reply(
    session,
    bot: Bot,
    report: Report,
    admin_id: int,
    body: str,
) -> bool:
    repo = ReportRepo(session)
    delivered = False
    reporter = await UserRepo(session).get_by_tele_id(report.reporter_id)
    text = _reply_text(report, reporter, body)

    async def _send(chat_id: int, reply_to_message_id: int | None = None):
        kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_to_message_id is not None:
            kwargs["reply_to_message_id"] = reply_to_message_id
            kwargs["allow_sending_without_reply"] = True
        return await bot.send_message(**kwargs)

    try:
        if report.origin_chat_id:
            try:
                reply = await _send(report.origin_chat_id, report.origin_message_id)
            except Exception:
                # The origin message can be deleted or the group removed from
                # the bot. In that case deliver privately rather than losing
                # the admin's response.
                logger.warning("origin delivery failed for report %s; using DM", report.id)
                reply = await _send(report.reporter_id)
        else:
            reply = await _send(report.reporter_id)
        delivered = True
        await repo.add_message(
            report.id,
            admin_id,
            "admin",
            body,
            delivered=True,
            delivery_chat_id=reply.chat.id,
            delivery_message_id=reply.message_id,
        )
    except Exception:
        logger.exception("could not deliver report %s reply", report.id)
        await repo.add_message(report.id, admin_id, "admin", body, delivered=False)
    await repo.add_event(report.id, admin_id, "replied", f"delivered={delivered}")
    return delivered