from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, String, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from app.core.database import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)

    # --- Tenant ---
    tenant_id = Column(Integer, nullable=True)  # nullable для обратной совместимости

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_settings_tenant"),)

    # --- Название бонусов ---
    bonus_name = Column(String(40), default="баллы", nullable=False)

    # --- Earn (%) по тирам ---
    earn_bronze_percent = Column(Integer, default=3, nullable=False)
    earn_silver_percent = Column(Integer, default=5, nullable=False)
    earn_gold_percent   = Column(Integer, default=7, nullable=False)

    # --- Приветственный бонус ---
    welcome_bonus_percent = Column(Integer, default=0, nullable=False)

    # --- Redeem ---
    redeem_max_percent = Column(Integer, default=30, nullable=False)

    # --- Активация ---
    activation_days = Column(Integer, default=0, nullable=False)

    # --- Сгорание ---
    burn_days    = Column(Integer, default=180, nullable=False)
    burn_percent = Column(Integer, default=100, nullable=False)

    # --- День рождения ---
    birthday_bonus_amount      = Column(Integer, default=5000, nullable=False)
    birthday_bonus_days_before = Column(Integer, default=7, nullable=False)
    birthday_bonus_ttl_days    = Column(Integer, default=30, nullable=False)
    birthday_notify_7d  = Column(Boolean, default=True, nullable=False)
    birthday_notify_3d  = Column(Boolean, default=True, nullable=False)
    birthday_notify_1d  = Column(Boolean, default=True, nullable=False)
    birthday_message    = Column(Text, nullable=True)
    birthday_message_7d = Column(Text, nullable=True)
    birthday_enabled    = Column(Boolean, default=True, nullable=False)

    # --- Пороги тиров (Bronze → Silver → Gold) ---
    silver_threshold = Column(Integer, default=50000,  nullable=False)
    gold_threshold   = Column(Integer, default=200000, nullable=False)

    # --- Тиры — JSONB (legacy) ---
    tiers_json = Column(JSONB, nullable=True)

    # --- Повышенный бонус ---
    boost_enabled   = Column(Boolean, default=False, nullable=False)
    boost_percent   = Column(Integer, default=7, nullable=False)
    boost_always    = Column(Boolean, default=False, nullable=False)
    boost_time_from = Column(String(5), nullable=True)
    boost_time_to   = Column(String(5), nullable=True)
    boost_mode      = Column(String(10), default="days", nullable=False)
    boost_weekdays  = Column(JSONB, nullable=True)   # было Text
    boost_dates     = Column(JSONB, nullable=True)   # было Text

    # --- ROI ---
    cost_per_lead   = Column(Integer, default=0, nullable=False)
    cost_per_client = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)