from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from DB.models.broadcast import Broadcast


class BroadcastRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        created_by: int,
        audience: str,
        body: str,
        parse_mode: str | None = None,
    ) -> Broadcast:
        row = Broadcast(
            created_by=created_by,
            audience=audience,
            body=body,
            parse_mode=parse_mode,
            status="queued",
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, broadcast_id: int) -> Broadcast | None:
        return await self.session.get(Broadcast, broadcast_id)

    async def list(self, limit: int = 50) -> Sequence[Broadcast]:
        query = (
            select(Broadcast)
            .order_by(Broadcast.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def claim(self, broadcast: Broadcast, total_targets: int) -> Broadcast:
        broadcast.status = "running"
        broadcast.total_targets = total_targets
        broadcast.started_at = datetime.now(timezone.utc)
        await self.session.flush()
        return broadcast

    async def record_result(
        self,
        broadcast: Broadcast,
        sent: int,
        failed: int,
        error: str | None = None,
    ) -> Broadcast:
        broadcast.sent_count = sent
        broadcast.failed_count = failed
        broadcast.last_error = error
        broadcast.finished_at = datetime.now(timezone.utc)
        broadcast.status = "completed" if failed == 0 else "completed_with_errors"
        await self.session.flush()
        return broadcast

    async def fail(self, broadcast: Broadcast, error: str) -> Broadcast:
        broadcast.status = "failed"
        broadcast.last_error = error[:2000]
        broadcast.finished_at = datetime.now(timezone.utc)
        await self.session.flush()
        return broadcast