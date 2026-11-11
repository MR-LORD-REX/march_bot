from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from DB.models.reports import Report, ReportEvent, ReportMessage


class ReportRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, report_id: int) -> Report | None:
        return await self.session.get(Report, report_id)

    async def get_open_for_origin(
        self,
        reporter_id: int,
        report_type: str,
        origin_chat_id: int | None,
        origin_message_id: int | None,
    ) -> Report | None:
        query = (
            select(Report)
            .where(
                Report.reporter_id == reporter_id,
                Report.report_type == report_type,
                Report.status.in_(["open", "claimed"]),
            )
            .order_by(Report.created_at.desc())
            .limit(1)
        )
        if origin_chat_id is not None:
            query = query.where(Report.origin_chat_id == origin_chat_id)
        if origin_message_id is not None:
            query = query.where(Report.origin_message_id == origin_message_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create(
        self,
        reporter_id: int,
        report_type: str,
        uid: int = 0,
        origin_chat_id: int | None = None,
        origin_message_id: int | None = None,
    ) -> Report:
        report = Report(
            reporter_id=reporter_id,
            report_type=report_type,
            uid=uid,
            origin_chat_id=origin_chat_id,
            origin_message_id=origin_message_id,
        )
        self.session.add(report)
        await self.session.flush()
        await self.add_event(report.id, None, "created", f"type={report_type}")
        return report

    async def add_message(
        self,
        report_id: int,
        author_id: int | None,
        direction: str,
        body: str,
        delivered: bool = False,
        delivery_chat_id: int | None = None,
        delivery_message_id: int | None = None,
    ) -> ReportMessage:
        message = ReportMessage(
            report_id=report_id,
            author_id=author_id,
            direction=direction,
            body=body,
            delivered=delivered,
            delivery_chat_id=delivery_chat_id,
            delivery_message_id=delivery_message_id,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def add_event(
        self,
        report_id: int,
        actor_id: int | None,
        event: str,
        detail: str | None = None,
    ) -> ReportEvent:
        entry = ReportEvent(
            report_id=report_id,
            actor_id=actor_id,
            event=event,
            detail=detail,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def set_admin_message(
        self,
        report: Report,
        chat_id: int,
        message_id: int,
    ) -> Report:
        report.admin_chat_id = chat_id
        report.admin_message_id = message_id
        await self.session.flush()
        return report

    async def claim(self, report: Report, actor_id: int) -> Report:
        report.status = "claimed"
        report.assigned_to = actor_id
        await self.add_event(report.id, actor_id, "claimed")
        await self.session.flush()
        return report

    async def resolve(self, report: Report, actor_id: int) -> Report:
        from datetime import datetime, timezone

        report.status = "resolved"
        report.resolved_at = datetime.now(timezone.utc)
        await self.add_event(report.id, actor_id, "resolved")
        await self.session.flush()
        return report

    async def close(self, report: Report, actor_id: int) -> Report:
        report.status = "closed"
        await self.add_event(report.id, actor_id, "closed")
        await self.session.flush()
        return report

    async def get_with_timeline(self, report_id: int) -> Report | None:
        query = (
            select(Report)
            .where(Report.id == report_id)
            .options(
                selectinload(Report.messages),
                selectinload(Report.events),
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_open(self, limit: int = 25) -> Sequence[Report]:
        query = (
            select(Report)
            .where(Report.status.in_(["open", "claimed"]))
            .order_by(Report.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()