from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, String, Boolean, Text
from app.core.database import Base


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)

    # --- Название бонусов (кастомное) ---
    bonus_name = Column(String(40), default="баллы", nullable=False)

    # --- Earn (%) по тирам ---
    earn_bronze_percent = Column(Integer, default=3, nullable=False)
    earn_silver_percent = Column(Integer, default=5, nullable=False)
    earn_gold_percent   = Column(Integer, default=7, nullable=False)

    # --- Приветственный бонус ---
    welcome_bonus_percent = Column(Integer, default=0, nullable=False)  # % от первой покупки (0 = выкл)

    # --- Redeem (списание) ---
    redeem_max_percent = Column(Integer, default=30, nullable=False)  # 0–100

    # --- Активация ---
    activation_days = Column(Integer, default=0, nullable=False)   # 0 = сразу

    # --- Сгорание ---
    burn_days = Column(Integer, default=180, nullable=False)
    burn_percent = Column(Integer, default=100, nullable=False)     # % сгорания (100 = всё)

    # --- День рождения ---
    birthday_bonus_amount   = Column(Integer, default=5000, nullable=False)
    birthday_bonus_days_before = Column(Integer, default=7, nullable=False)
    birthday_bonus_ttl_days = Column(Integer, default=30, nullable=False)
    birthday_notify_7d  = Column(Boolean, default=True, nullable=False)
    birthday_notify_3d  = Column(Boolean, default=True, nullable=False)
    birthday_notify_1d  = Column(Boolean, default=True, nullable=False)
    birthday_message    = Column(Text, nullable=True)
    birthday_message_7d = Column(Text, nullable=True)
    birthday_enabled    = Column(Boolean, default=True, nullable=False)

    # --- Тиры (динамические, JSON-список) ---
    # Хранится как JSON строка: [{"name":"Silver","spend_from":300000,"bonus_percent":5}, ...]
    # Bronze — всегда базовый (earn_bronze_percent), тиры выше задаются здесь
    tiers_json = Column(Text, nullable=True)   # JSON

    # --- Накопительный (повышенный) бонус ---
    boost_enabled     = Column(Boolean, default=False, nullable=False)
    boost_percent     = Column(Integer, default=7, nullable=False)
    boost_always      = Column(Boolean, default=False, nullable=False)
    boost_time_from   = Column(String(5), nullable=True)   # "HH:MM"
    boost_time_to     = Column(String(5), nullable=True)
    boost_mode        = Column(String(10), default="days", nullable=False)
    boost_weekdays    = Column(Text, nullable=True)
    boost_dates       = Column(Text, nullable=True)
    cost_per_lead     = Column(Integer, default=0, nullable=False)
    cost_per_client   = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
