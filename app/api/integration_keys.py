import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_utils import get_tenant_ids_for_user
from app.models.auth import AuthUser, Tenant
from app.models.integration_key import IntegrationKey
from app.schemas.integration import KeyCreate, KeyCreated, KeyOut
from app.services.loyalty_engine import resolve_network_id


def owner(request: Request, db: Session = Depends(get_db)):
    user = getattr(request.state, "user", None) or {}
    if not user.get("tenant_id"):
        raise HTTPException(401, "Не авторизован")
    if user.get("role") != "owner":
        raise HTTPException(403, "Управлять API-ключами может только владелец")
    account = db.get(AuthUser, user.get("id"))
    if account is None or not account.is_active or account.role != "owner":
        raise HTTPException(403, "Доступ владельца больше недействителен")
    home = db.get(Tenant, account.tenant_id)
    active = db.get(Tenant, int(user["tenant_id"]))
    if (home is None or active is None or not home.is_active or not active.is_active
            or (home.id != active.id and (home.parent_tenant_id is not None or active.parent_tenant_id != home.id))):
        raise HTTPException(403, "Недоступный филиал")
    return user


router = APIRouter(prefix="/accounts/integration-keys", tags=["integration keys"], dependencies=[Depends(owner)])


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.get("", response_model=list[KeyOut])
def list_keys(request: Request, response: Response, db: Session = Depends(get_db)):
    no_store(response)
    ids = get_tenant_ids_for_user(request, db)
    return db.scalars(select(IntegrationKey).where(IntegrationKey.tenant_id.in_(ids))
                      .order_by(IntegrationKey.id.desc())).all()


@router.post("", response_model=KeyCreated, status_code=201)
def create_key(payload: KeyCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    no_store(response)
    user = owner(request, db)
    tenant_id = payload.tenant_id or int(user["tenant_id"])
    if tenant_id not in get_tenant_ids_for_user(request, db):
        raise HTTPException(403, "Недоступный филиал")
    tenant = db.get(Tenant, tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(403, "Филиал недоступен")
    public_id = secrets.token_hex(8)
    token = f"ltv_live_{public_id}.{secrets.token_urlsafe(32)}"
    key = IntegrationKey(
        public_id=public_id, token_hash=hashlib.sha256(token.encode()).hexdigest(), name=payload.name,
        tenant_id=tenant_id, network_id=resolve_network_id(db, tenant_id), created_by_id=user.get("id"),
        scopes=payload.scopes, expires_at=datetime.utcnow() + timedelta(days=payload.expires_in_days),
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return KeyCreated(key=KeyOut.model_validate(key), token=token)


@router.delete("/{key_id}", response_model=KeyOut)
def revoke_key(key_id: int, request: Request, response: Response, db: Session = Depends(get_db)):
    no_store(response)
    ids = get_tenant_ids_for_user(request, db)
    key = db.scalar(select(IntegrationKey).where(IntegrationKey.id == key_id, IntegrationKey.tenant_id.in_(ids)).with_for_update())
    if key is None:
        raise HTTPException(404, "API-ключ не найден")
    if key.revoked_at is None:
        key.revoked_at = datetime.utcnow()
        db.commit()
        db.refresh(key)
    return key
