from sqlalchemy import Column , String , Integer , BIGINT , BOOLEAN
from sqlalchemy.orm import Mapped , mapped_column , relationship

from bot.DB.base import base

class TeleGroup(base):
    __tablename__="telegram_groups"
    
    group_id:Mapped[int]=mapped_column(BIGINT,unique=True,primary_key=True)
    group_name:Mapped[str]=mapped_column(String,nullable=True)
    banned:Mapped[bool]=mapped_column(BOOLEAN,default=False)
    
    users: Mapped[list["UsersInGroup"]] = relationship("UsersInGroup", back_populates="group", cascade="all, delete-orphan")