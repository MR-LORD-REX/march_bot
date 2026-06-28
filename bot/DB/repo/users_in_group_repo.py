from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Sequence
import logging

from bot.DB.repo.base import BaseRepo
from bot.DB.models.users_in_gc import UsersInGroup
from bot.DB.models.users import Users
from bot.DB.models.tele_group import TeleGroup

logger = logging.getLogger(__name__)

class UsersInGroupRepo(BaseRepo):
    def __init__(self, session: AsyncSession):
        super().__init__(UsersInGroup, session)
        self.model: type[UsersInGroup] = UsersInGroup
    
    async def _find_user_in_group(self, user_id: int, group_id: int, with_relations: bool = False) -> UsersInGroup | None:
        query = select(self.model).where(
            (self.model.user_id == user_id) & (self.model.group_id == group_id)
        )
        if with_relations:
            query = query.options(
                selectinload(self.model.user),
                selectinload(self.model.group)
            )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def add_user_to_group(self, user_id: int, group_id: int) -> bool:
        existing = await self._find_user_in_group(user_id, group_id)
        
        if existing:
            logger.warning(f"user {user_id} already in group {group_id}")
            return False
        
        user_in_group = UsersInGroup(user_id=user_id, group_id=group_id)
        await self.add(user_in_group)
        await self.session.commit()
        return True
    
    async def remove_user_from_group(self, user_id: int, group_id: int) -> bool:
        user_in_group = await self._find_user_in_group(user_id, group_id)
        
        if not user_in_group:
            logger.warning(f"user {user_id} not found in group {group_id}")
            return False
        
        await self.delete(user_in_group)
        await self.session.commit()
        return True
    
    async def is_user_in_group(self, user_id: int, group_id: int) -> bool:
        result = await self._find_user_in_group(user_id, group_id)
        return result is not None
    
    async def get_user_in_group(self, user_id: int, group_id: int) -> UsersInGroup | None:
        return await self._find_user_in_group(user_id, group_id, with_relations=True)
    
    async def get_user_groups(self, user_id: int) -> Sequence[UsersInGroup]:
        query = select(self.model).where(self.model.user_id == user_id).options(
            selectinload(UsersInGroup.group)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_group_users(self, group_id: int) -> Sequence[UsersInGroup]:
        query = select(self.model).where(self.model.group_id == group_id).options(
            selectinload(UsersInGroup.user)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_all_grouped_by_group(self) -> dict[int, set[int]]:
        """Returns dict of {group_id: set of user_ids} for all groups"""
        all_user_group = await self.get_all()
        grouped: dict[int, set[int]] = {}
        
        for ug in all_user_group:
            if ug.group_id not in grouped:
                grouped[ug.group_id] = set()
            grouped[ug.group_id].add(ug.user_id)
        
        return grouped
