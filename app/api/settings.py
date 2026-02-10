# app/api/settings.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings as env_settings
from app.models.settings import Settings
from app.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def get_or_create_settings(db: Session) -> Settings:
    row = db.query(Settings).order_by(Settings.id.asc()).first()
    if row:
        return row

    row = Settings(
        earn_bronze_percent=int(env_settings.BONUS_PERCENT_BRONZE),
        earn_silver_percent=int(env_settings.BONUS_PERCENT_SILVER),
        earn_gold_percent=int(env_settings.BONUS_PERCENT_GOLD),
        redeem_max_percent=int(env_settings.REDEEM_MAX_PERCENT),
        activation_days=int(env_settings.BONUS_ACTIVATION_DAYS),
        burn_days=int(env_settings.BONUS_BURN_DAYS),
        birthday_bonus_amount=int(env_settings.BDAY_BONUS_AMOUNT),
        birthday_bonus_days_before=7,
        birthday_bonus_ttl_days=30,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("", response_model=SettingsOut, include_in_schema=False)
@router.get("/", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> SettingsOut:
    row = get_or_create_settings(db)
    return SettingsOut.model_validate(row)


@router.put("", response_model=SettingsOut, include_in_schema=False)
@router.put("/", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsOut:
    row = get_or_create_settings(db)

    row.earn_bronze_percent = payload.earn_bronze_percent
    row.earn_silver_percent = payload.earn_silver_percent
    row.earn_gold_percent = payload.earn_gold_percent

    row.redeem_max_percent = payload.redeem_max_percent

    row.activation_days = payload.activation_days
    row.burn_days = payload.burn_days

    row.birthday_bonus_amount = payload.birthday_bonus_amount
    row.birthday_bonus_days_before = payload.birthday_bonus_days_before
    row.birthday_bonus_ttl_days = payload.birthday_bonus_ttl_days

    db.commit()
    db.refresh(row)
    return SettingsOut.model_validate(row)
