from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.settings_schema import SettingsOut, SettingsUpdate
from app.services.loyalty_engine import get_or_create_settings

router = APIRouter(prefix="/settings", tags=["settings"])


def must_owner(request: Request) -> None:
    u = getattr(request.state, "user", None) or {}
    if not u:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if str(u.get("role") or "").lower() != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")


def _tenant_id_from_request(request: Request) -> int | None:
    """
    Настройки лояльности общие на сеть: возвращаем network_id (корень),
    чтобы правка настроек из контекста филиала меняла настройки сети.
    """
    u = getattr(request.state, "user", None) or {}
    tid = u.get("network_id") or u.get("tenant_id")
    return int(tid) if tid else None


@router.get("", response_model=SettingsOut, include_in_schema=False)
@router.get("/", response_model=SettingsOut)
def read_settings(request: Request, db: Session = Depends(get_db)) -> SettingsOut:
    tenant_id = _tenant_id_from_request(request)
    row = get_or_create_settings(db, tenant_id=tenant_id)
    return SettingsOut.model_validate(row)


@router.put("", response_model=SettingsOut, include_in_schema=False)
@router.put("/", response_model=SettingsOut)
def update_settings(payload: SettingsUpdate, request: Request, db: Session = Depends(get_db)) -> SettingsOut:
    must_owner(request)
    tenant_id = _tenant_id_from_request(request)
    row = get_or_create_settings(db, tenant_id=tenant_id)

    row.bonus_name = payload.bonus_name

    row.earn_bronze_percent = payload.earn_bronze_percent
    row.earn_silver_percent = payload.earn_silver_percent
    row.earn_gold_percent   = payload.earn_gold_percent

    row.welcome_bonus_percent = payload.welcome_bonus_percent
    row.redeem_max_percent    = payload.redeem_max_percent

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

    row.boost_enabled = payload.boost_enabled
    row.boost_percent = payload.boost_percent
    row.boost_always  = payload.boost_always
    row.boost_mode    = payload.boost_mode or "days"

    row.boost_weekdays = payload.boost_weekdays
    row.boost_dates    = payload.boost_dates

    row.silver_threshold = payload.silver_threshold
    row.gold_threshold   = payload.gold_threshold
    row.cost_per_lead   = payload.cost_per_lead
    row.cost_per_client = payload.cost_per_client

    row.tiers_json = [t.model_dump() for t in payload.tiers]

    db.commit()
    db.refresh(row)
    return SettingsOut.model_validate(row)