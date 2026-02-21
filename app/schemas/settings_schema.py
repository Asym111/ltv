# app/schemas/settings_schema.py
from __future__ import annotations

import json
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class TierItem(BaseModel):
    name: str
    spend_from: int = Field(ge=0)
    bonus_percent: int = Field(ge=0, le=100)


class SettingsOut(BaseModel):
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
    cost_per_lead:   int = 0
    cost_per_client: int = 0
    tiers: list[TierItem] = []

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

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    bonus_name: str = Field(default="баллы", max_length=40)
    earn_bronze_percent: int = Field(default=3, ge=0, le=100)
    earn_silver_percent: int = Field(default=5, ge=0, le=100)
    earn_gold_percent:   int = Field(default=7, ge=0, le=100)
    welcome_bonus_percent: int = Field(default=0, ge=0, le=100)
    redeem_max_percent: int = Field(default=30, ge=0, le=100)
    activation_days: int = Field(default=0, ge=0, le=365)
    burn_days:       int = Field(default=180, ge=1, le=3650)
    burn_percent:    int = Field(default=100, ge=1, le=100)
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
    boost_mode:     str  = Field(default="days", pattern="^(days|dates)$")
    boost_weekdays: list[str] = []
    boost_dates:    list[str] = []
    cost_per_lead:   int = Field(default=0, ge=0)
    cost_per_client: int = Field(default=0, ge=0)
    tiers: list[TierItem] = []