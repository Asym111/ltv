from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings as env_settings
from app.models.settings_model import Settings
from app.schemas.settings_schema import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def get_or_create_settings(db: Session) -> Settings:
    row = db.query(Settings).order_by(Settings.id.asc()).first()
    if row:
        return row

    row = Settings(
        bonus_name="баллы",
        earn_bronze_percent=int(env_settings.BONUS_PERCENT_BRONZE),
        earn_silver_percent=int(env_settings.BONUS_PERCENT_SILVER),
        earn_gold_percent=int(env_settings.BONUS_PERCENT_GOLD),
        welcome_bonus_percent=0,
        redeem_max_percent=int(env_settings.REDEEM_MAX_PERCENT),
        activation_days=int(env_settings.BONUS_ACTIVATION_DAYS),
        burn_days=int(env_settings.BONUS_BURN_DAYS),
        burn_percent=100,
        birthday_bonus_amount=int(env_settings.BDAY_BONUS_AMOUNT),
        birthday_bonus_days_before=7,
        birthday_bonus_ttl_days=30,
        birthday_notify_7d=True,
        birthday_notify_3d=True,
        birthday_notify_1d=True,
        birthday_enabled=True,
        boost_enabled=False,
        boost_percent=7,
        boost_always=False,
        boost_mode="days",
        cost_per_lead=0,
        cost_per_client=0,
        tiers_json=json.dumps([
            {"name": "Silver", "spend_from": 300000, "bonus_percent": 5},
            {"name": "Gold",   "spend_from": 1000000, "bonus_percent": 7},
        ], ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=SettingsOut, include_in_schema=False)
@router.get("/", response_model=SettingsOut)
def read_settings(request: Request, db: Session = Depends(get_db)) -> SettingsOut:
    row = get_or_create_settings(db)
    return SettingsOut.model_validate(row)


@router.put("", response_model=SettingsOut, include_in_schema=False)
@router.put("/", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsOut:
    row = get_or_create_settings(db)

    row.bonus_name = payload.bonus_name

    row.earn_bronze_percent = payload.earn_bronze_percent
    row.earn_silver_percent = payload.earn_silver_percent
    row.earn_gold_percent   = payload.earn_gold_percent

    row.welcome_bonus_percent = payload.welcome_bonus_percent

    row.redeem_max_percent = payload.redeem_max_percent

    row.activation_days = payload.activation_days
    row.burn_days       = payload.burn_days
    row.burn_percent    = payload.burn_percent

    row.birthday_bonus_amount      = payload.birthday_bonus_amount
    row.birthday_bonus_days_before = payload.birthday_bonus_days_before
    row.birthday_bonus_ttl_days    = payload.birthday_bonus_ttl_days
    row.birthday_notify_7d  = payload.birthday_notify_7d
    row.birthday_notify_3d  = payload.birthday_notify_3d
    row.birthday_notify_1d  = payload.birthday_notify_1d
    row.birthday_message    = payload.birthday_message
    row.birthday_message_7d = payload.birthday_message_7d
    row.birthday_enabled    = payload.birthday_enabled

    row.boost_enabled   = payload.boost_enabled
    row.boost_percent   = payload.boost_percent
    row.boost_always    = payload.boost_always

    # Новые поля расписания буста
    if hasattr(payload, 'boost_mode') and payload.boost_mode is not None:
        row.boost_mode = payload.boost_mode
    if hasattr(payload, 'boost_weekdays') and payload.boost_weekdays is not None:
        row.boost_weekdays = json.dumps(payload.boost_weekdays, ensure_ascii=False)
    if hasattr(payload, 'boost_dates') and payload.boost_dates is not None:
        row.boost_dates = json.dumps(payload.boost_dates, ensure_ascii=False)

    # ROI поля
    if hasattr(payload, 'cost_per_lead') and payload.cost_per_lead is not None:
        row.cost_per_lead = payload.cost_per_lead
    if hasattr(payload, 'cost_per_client') and payload.cost_per_client is not None:
        row.cost_per_client = payload.cost_per_client

    # Тиры → JSON
    row.tiers_json = json.dumps(
        [t.model_dump() for t in payload.tiers],
        ensure_ascii=False,
    )

    db.commit()
    db.refresh(row)
    return SettingsOut.model_validate(row)