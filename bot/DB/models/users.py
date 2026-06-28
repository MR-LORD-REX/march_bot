from sqlalchemy import Column , String , Integer , BIGINT
from sqlalchemy.orm import Mapped , mapped_column , relationship

from bot.DB.base import base
from bot.DB.models.cache import Cache
from bot.DB.models.game_ids import GameID
from bot.DB.models.user_settings import UserSettings

class Users(base):
    __tablename__='users'

    telegram_id:Mapped[int]=mapped_column(BIGINT,primary_key=True)
    username:Mapped[str]=mapped_column(String(255))
    display_name:Mapped[str]=mapped_column(String(255))
    banned:Mapped[bool]=mapped_column(default=False)
    warns:Mapped[int]=mapped_column(Integer,default=0)
    
    cache: Mapped[list["Cache"]] = relationship("Cache", back_populates="user", cascade="all, delete-orphan")
    game_ids: Mapped[list["GameID"]] = relationship("GameID", back_populates="user", cascade="all, delete-orphan")
    settings: Mapped["UserSettings"] = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
    groups: Mapped[list["UsersInGroup"]] = relationship("UsersInGroup", back_populates="user", cascade="all, delete-orphan")