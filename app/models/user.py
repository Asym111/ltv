from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Column, Integer, String, Date, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    phone = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)

    tier = Column(String, default="Bronze", nullable=False)

    # Это "активный" баланс для UI/CRM.
    # Источник правды — гранты, но это кэш для удобства (будем синхронизировать).
    bonus_balance = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transactions = relationship("Transaction", back_populates="user")
    bonus_grants = relationship("BonusGrant", back_populates="user")
