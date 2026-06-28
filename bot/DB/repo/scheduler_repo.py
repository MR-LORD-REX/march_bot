from typing import Sequence
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta , timezone
import logging


from bot.DB.repo.base import BaseRepo
from bot.DB.models.scheduler import SchedulerMeta

logger=logging.getLogger(__name__)

class SchedulerRepo(BaseRepo):
    
    def __init__(self, session: AsyncSession):
        super().__init__(SchedulerMeta, session)
        self.model: type[SchedulerMeta] = SchedulerMeta
        
    async def add_task_meta(
        self,
        user_id: int,
        task_id: str,
        task_name: str,
        task_type: str,
        execution_time: datetime ,
        args: dict|None = None,
        kwargs: dict|None = None,
    ) -> SchedulerMeta| None:
        existing_meta = await self.get_task_meta(task_id)
        if existing_meta:
            raise ValueError(f"Task with ID '{task_id}' already exists.")
        new_meta = SchedulerMeta(
            user_id=user_id,
            task_id=task_id,
            task_name=task_name,
            task_type=task_type,
            args=args,
            kwargs=kwargs,
            execution_time=execution_time or datetime.now(timezone.utc) + timedelta(seconds=10)  # default to 10 seconds later if not provided
        )
        await self.add(new_meta)
        await self.session.commit()
        return new_meta
    
    async def get_task_meta(self, task_id: str) -> SchedulerMeta | None:
        query = select(self.model).where(self.model.task_id == task_id)
        result = await self.session.execute(query)
        meta = result.scalar_one_or_none()
        return meta
    
    async def delete_task_meta(self, task_id: str) -> bool:
        meta = await self.get_task_meta(task_id)
        if not meta:
            logger.warning(f"Task with ID '{task_id}' not found for deletion.")
            return False
        await self.delete(meta)
        await self.session.commit()
        return True
    
    async def get_all_tasks(self) -> Sequence[SchedulerMeta]:
        query = select(self.model)
        result = await self.session.execute(query)
        tasks = result.scalars().all()
        return tasks