from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings as env_settings
from app.models.settings_model import Settings
from app.schemas.settings_schema import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def must_owner(request: Request) -> None:
    u = getattr(request.state, "user", None) or {}
    if not u:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if str(u.get("role") or "").lower() != "owner":
        raise HTTPException(status_code=403, detail="Owner role required")


def _tenant_id_from_request(request: Request) -> int | None:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    return int(tid) if tid else None


def get_or_create_settings(db: Session, tenant_id: int | None = None) -> Settings:
    """
    Получает настройки для тенанта.
    Если своих настроек нет — копирует из глобальных (tenant_id IS NULL).
    """
    # Ищем настройки тенанта
    if tenant_id:
        row = db.query(Settings).filter(Settings.tenant_id == tenant_id).first()
        if row:
            return row
        # Берём глобальные как шаблон
        template = db.query(Settings).filter(Settings.tenant_id == None).first()  # noqa: E711
    else:
        row = db.query(Settings).filter(Settings.tenant_id == None).first()  # noqa: E711
        if row:
            return row
        template = None

    # Собираем defaults из шаблона или env
    d = {}
    if template:
        for col in template.__table__.columns:
            if col.name not in ("id", "tenant_id", "created_at"):
                d[col.name] = getattr(template, col.name)

    row = Settings(
        tenant_id=tenant_id,
        bonus_name=d.get("bonus_name", "баллы"),
        earn_bronze_percent=d.get("earn_bronze_percent", int(env_settings.BONUS_PERCENT_BRONZE)),
        earn_silver_percent=d.get("earn_silver_percent", int(env_settings.BONUS_PERCENT_SILVER)),
        earn_gold_percent=d.get("earn_gold_percent",   int(env_settings.BONUS_PERCENT_GOLD)),
        welcome_bonus_percent=d.get("welcome_bonus_percent", 0),
        redeem_max_percent=d.get("redeem_max_percent", int(env_settings.REDEEM_MAX_PERCENT)),
        activation_days=d.get("activation_days", int(env_settings.BONUS_ACTIVATION_DAYS)),
        burn_days=d.get("burn_days", int(env_settings.BONUS_BURN_DAYS)),
        burn_percent=d.get("burn_percent", 100),
        birthday_bonus_amount=d.get("birthday_bonus_amount", int(env_settings.BDAY_BONUS_AMOUNT)),
        birthday_bonus_days_before=d.get("birthday_bonus_days_before", 7),
        birthday_bonus_ttl_days=d.get("birthday_bonus_ttl_days", 30),
        birthday_notify_7d=d.get("birthday_notify_7d", True),
        birthday_notify_3d=d.get("birthday_notify_3d", True),
        birthday_notify_1d=d.get("birthday_notify_1d", True),
        birthday_enabled=d.get("birthday_enabled", True),
        boost_enabled=d.get("boost_enabled", False),
        boost_percent=d.get("boost_percent", 7),
        boost_always=d.get("boost_always", False),
        boost_mode=d.get("boost_mode", "days"),
        boost_weekdays=d.get("boost_weekdays"),
        boost_dates=d.get("boost_dates"),
        silver_threshold=d.get("silver_threshold", 50000),
        gold_threshold=d.get("gold_threshold", 200000),
        cost_per_lead=d.get("cost_per_lead", 0),
        cost_per_client=d.get("cost_per_client", 0),
        tiers_json=d.get("tiers_json"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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