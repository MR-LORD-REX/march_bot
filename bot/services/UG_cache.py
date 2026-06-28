from typing import Callable, Awaitable, Any , Dict 
from collections import defaultdict
from pydantic import BaseModel , ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from bot.DB.repo.user_repo import UserRepo
from bot.DB.repo.users_in_group_repo import UsersInGroupRepo
from bot.DB.repo.tele_group_repo import TeleGroupRepo

logger=logging.getLogger(__name__)

class Auser(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    tele_id:int
    username:str|None
    display_name:str|None
    
class Agroup(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    group_id:int
    members:set[int]

class UsersRecord:
    def __init__(self):
        self._record:Dict[int,Auser]={}
        
    def is_registered(self,tele_id:int)->bool:
        return tele_id in self._record
    
    def get_user(self,tele_id:int)->Auser|None:
        return self._record.get(tele_id)
    
    def get_username(self,tele_id:int)->str|None:
        user=self.get_user(tele_id)
        if user:
            return user.username
        return None
    
    def get_display_name(self,tele_id:int)->str|None:
        user=self.get_user(tele_id)
        if user:
            return user.display_name
        return None
    
class GroupsRecord:
    def __init__(self):
        self._record:Dict[int,Agroup]={}
        
    def is_registered(self,group_id:int)->bool:
        return group_id in self._record

    def get_group(self,group_id:int)->Agroup|None:
        return self._record.get(group_id)
    
    def is_user_in_group(self,tele_id:int,group_id:int)->bool:
        group=self.get_group(group_id)
        if group:
            return tele_id in group.members
        return False
        
    
async def load_users(
    session:AsyncSession,
    record:UsersRecord
    )->None:
    all_users=await UserRepo(session).get_all()
    new={}
    for user in all_users:
        new[user.telegram_id]=Auser(
            tele_id=user.telegram_id,
            username=user.username,
            display_name=user.display_name
        )
    record._record=new
    
async def load_groups(session, record:GroupsRecord)->None:
    groups = await TeleGroupRepo(session).get_all()
    memberships = await UsersInGroupRepo(session).get_all_grouped_by_group()

    new = {}

    for group in groups:
        new[group.group_id] = Agroup(
            group_id=group.group_id,
            members=memberships.get(group.group_id, set())
        )

    record._record = new