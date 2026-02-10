from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime
from app.core.database import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)

    # Earn (%)
    earn_bronze_percent = Column(Integer, default=3, nullable=False)
    earn_silver_percent = Column(Integer, default=5, nullable=False)
    earn_gold_percent   = Column(Integer, default=7, nullable=False)

    # Redeem
    redeem_max_percent = Column(Integer, default=30, nullable=False)  # 0–100

    # Activation / Burn
    activation_days = Column(Integer, default=7, nullable=False)
    burn_days = Column(Integer, default=180, nullable=False)

    # Birthday
    birthday_bonus_amount = Column(Integer, default=5000, nullable=False)
    birthday_bonus_days_before = Column(Integer, default=7, nullable=False)
    birthday_bonus_ttl_days = Column(Integer, default=30, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
