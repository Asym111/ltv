from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # ✅ tenant-изоляция клиентов
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # ❗️В мульти-аккаунте phone НЕ должен быть unique глобально
    phone = Column(String, index=True, nullable=False)

    full_name = Column(String, nullable=True)
    birth_date = Column(Date, nullable=True)

    tier = Column(String, default="Bronze", nullable=False)

    bonus_balance = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transactions = relationship("Transaction", back_populates="user")
    bonus_grants = relationship("BonusGrant", back_populates="user")
