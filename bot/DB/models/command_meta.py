from sqlalchemy import Boolean, Integer, String, BIGINT, ForeignKey , Enum , Index
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column


from bot.DB.base import base

class CommandsMeta(base):
    __tablename__="commands_meta"
    
    id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    cmd:Mapped[str]=mapped_column(String,unique=True)
    active:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)