from __future__ import annotations

from sqlalchemy import Column, Integer, String , Boolean , BIGINT , ForeignKey , Text, Enum , Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import DateTime
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy import UniqueConstraint

from bot.DB.base import base

class Cache(base):
    __tablename__='cache'

    id:Mapped[int]=mapped_column(Integer,primary_key=True)
    telegram_id:Mapped[int]=mapped_column(BIGINT,ForeignKey('users.telegram_id'))
    file_id:Mapped[str]=mapped_column(String(255))
    data:Mapped[str]=mapped_column(String(800),nullable=True)
    slot:Mapped[int]=mapped_column(Integer,nullable=True)
    type:Mapped[str]=mapped_column(Enum('PFP','CHAR','MOC','PF','ANO','AS',name='cache_type'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped["Users"] = relationship("Users", back_populates="cache")
    
    __table_args__ = (
        Index(
            'uq_cache_char',
            'telegram_id', 'type', 'slot',
            unique=True,
            postgresql_where=(Column('type') == 'CHAR'),
        ),
        Index(
            'uq_cache_non_char',
            'telegram_id', 'type',
            unique=True,
            postgresql_where=(Column('type') != 'CHAR'),
        ),
    )
    