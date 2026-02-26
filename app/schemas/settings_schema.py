# app/schemas/settings_schema.py
from __future__ import annotations
import json
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class TierItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    spend_from: int = Field(ge=0)
    bonus_percent: int = Field(ge=0, le=100)


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore", populate_by_name=True)

    id: int = 1
    bonus_name: str = "баллы"
    earn_bronze_percent: int = 3
    earn_silver_percent: int = 5
    earn_gold_percent:   int = 7
    welcome_bonus_percent: int = 0
    redeem_max_percent: int = 30
    activation_days: int = 0
    burn_days:       int = 180
    burn_percent:    int = 100
    birthday_bonus_amount:      int  = 5000
    birthday_bonus_days_before: int  = 7
    birthday_bonus_ttl_days:    int  = 30
    birthday_notify_7d:  bool = True
    birthday_notify_3d:  bool = True
    birthday_notify_1d:  bool = True
    birthday_message:    Optional[str] = None
    birthday_message_7d: Optional[str] = None
    birthday_enabled:    bool = True
    boost_enabled:  bool = False
    boost_percent:  int  = 7
    boost_always:   bool = False
    boost_mode:     str  = "days"
    boost_weekdays: list[str] = []
    boost_dates:    list[str] = []
    silver_threshold: int = 50000
    gold_threshold:   int = 200000
    cost_per_lead:   int = 0
    cost_per_client: int = 0
    tiers: list[TierItem] = []

    @model_validator(mode="before")
    @classmethod
    def normalize_input(cls, data):
        # Конвертируем ORM объект в dict
        if hasattr(data, "__tablename__"):
            # Это SQLAlchemy ORM объект
            d = {}
            for col in data.__table__.columns:
                d[col.name] = getattr(data, col.name, None)
            # tiers_json -> tiers
            if "tiers_json" in d:
                d["tiers"] = d.pop("tiers_json") or "[]"
            return d
        # Обычный dict — просто маппим tiers_json если есть
        if isinstance(data, dict) and "tiers_json" in data:
            data = dict(data)
            data["tiers"] = data.pop("tiers_json") or "[]"
        return data

    @field_validator("boost_weekdays", "boost_dates", mode="before")
    @classmethod
    def parse_json_list(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return v or []

    @field_validator("tiers", mode="before")
    @classmethod
    def parse_tiers(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return v or []


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bonus_name: str = Field(default="баллы", max_length=40)
    earn_bronze_percent: int = Field(default=3, ge=0, le=100)
    earn_silver_percent: int = Field(default=5, ge=0, le=100)
    earn_gold_percent:   int = Field(default=7, ge=0, le=100)
    welcome_bonus_percent: int = Field(default=0, ge=0, le=100)
    redeem_max_percent: int = Field(default=30, ge=0, le=100)
    activation_days: int = Field(default=0, ge=0, le=365)
    burn_days:       int = Field(default=180, ge=1, le=3650)
    burn_percent:    int = Field(default=100, ge=0, le=100)
    birthday_bonus_amount:      int  = Field(default=5000, ge=0)
    birthday_bonus_days_before: int  = Field(default=7, ge=0, le=30)
    birthday_bonus_ttl_days:    int  = Field(default=30, ge=1, le=365)
    birthday_notify_7d:  bool = True
    birthday_notify_3d:  bool = True
    birthday_notify_1d:  bool = True
    birthday_message:    Optional[str] = None
    birthday_message_7d: Optional[str] = None
    birthday_enabled:    bool = True
    boost_enabled:  bool = False
    boost_percent:  int  = Field(default=7, ge=0, le=100)
    boost_always:   bool = False
    boost_mode:     str  = Field(default="days")
    boost_weekdays: list[str] = []
    boost_dates:    list[str] = []
    silver_threshold: int = Field(default=50000,  ge=0)
    gold_threshold:   int = Field(default=200000, ge=0)
    cost_per_lead:   int = Field(default=0, ge=0)
    cost_per_client: int = Field(default=0, ge=0)
    tiers: list[TierItem] = []