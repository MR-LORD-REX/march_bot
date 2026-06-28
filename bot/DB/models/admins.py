from sqlalchemy import Column, Integer, String, Boolean, ForeignKey , BIGINT , Enum
from sqlalchemy.orm import Mapped, mapped_column
from bot.DB.base import base

class Admins(base):
    __tablename__="admins"
    
    telegram_id:Mapped[int]=mapped_column(BIGINT,primary_key=True,nullable=False,unique=True)
    username:Mapped[str]=mapped_column(String,nullable=True)
    display_name:Mapped[str]=mapped_column(String,nullable=True)
    authority:Mapped[str]=mapped_column(
        Enum("basic","moderator","admin","owner",name="authority_type"),
        nullable=False,
        default="basic"
    )