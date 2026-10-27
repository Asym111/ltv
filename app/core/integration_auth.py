"""Bearer-only authentication, intentionally separate from browser sessions."""
import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import case, or_, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import Tenant
from app.models.integration_key import IntegrationKey


API_PREFIX = "/api/integration/v1"
RATE_LIMIT = 120
TOKEN_PATTERN = re.compile(r"^ltv_live_([a-f0-9]{16})\.[A-Za-z0-9_-]{43}$")
bearer = HTTPBearer(auto_error=False)


def is_integration_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


@dataclass(frozen=True)
class IntegrationContext:
    key_id: int
    tenant_id: int
    network_id: int
    scopes: tuple[str, ...]


def unauthorized():
    return HTTPException(401, "Недействительный API-ключ", headers={"WWW-Authenticate": "Bearer"})


def authenticate_integration(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> IntegrationContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    token = credentials.credentials
    match = TOKEN_PATTERN.fullmatch(token)
    if not match:
        raise unauthorized()
    key = db.scalar(select(IntegrationKey).where(IntegrationKey.public_id == match[1]))
    now = datetime.utcnow()
    if (key is None or not hmac.compare_digest(key.token_hash, hashlib.sha256(token.encode()).hexdigest())
            or key.revoked_at is not None or key.expires_at <= now):
        raise unauthorized()
    tenant = db.get(Tenant, key.tenant_id)
    root = db.get(Tenant, key.network_id)
    if (tenant is None or root is None or not tenant.is_active or not root.is_active
            or root.parent_tenant_id is not None
            or (tenant.id != root.id and tenant.parent_tenant_id != root.id)):
        raise HTTPException(403, "Организация или филиал недоступны")
    if root.access_until is not None and root.access_until <= now:
        raise HTTPException(403, "Срок доступа организации истёк")

    context = IntegrationContext(key.id, key.tenant_id, key.network_id, tuple(key.scopes))
    window = now.replace(second=0, microsecond=0)
    # Database counter shares the limit across workers; no process-local limiter.
    result = db.execute(update(IntegrationKey).where(
        IntegrationKey.id == key.id, IntegrationKey.revoked_at.is_(None),
        IntegrationKey.expires_at > now,
        or_(IntegrationKey.usage_window.is_(None), IntegrationKey.usage_window != window,
            IntegrationKey.usage_count < RATE_LIMIT),
    ).values(
        usage_window=window,
        usage_count=case((IntegrationKey.usage_window == window, IntegrationKey.usage_count + 1), else_=1),
        last_used_at=now,
    ).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        db.rollback()
        fresh = db.get(IntegrationKey, context.key_id, populate_existing=True)
        if fresh is None or fresh.revoked_at is not None or fresh.expires_at <= now:
            raise unauthorized()
        raise HTTPException(429, "Лимит запросов: 120 в минуту", headers={"Retry-After": str(60 - now.second)})
    db.commit()
    return context


def require_integration_scope(scope: str):
    def check(context: IntegrationContext = Depends(authenticate_integration)):
        if scope not in context.scopes:
            raise HTTPException(403, "У API-ключа нет разрешения на эту операцию")
        return context
    return check
