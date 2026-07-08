from __future__ import annotations

from fastapi import Request, HTTPException
from sqlalchemy.orm import Session

from app.models.auth import Tenant


def must_tenant_id(request: Request) -> int:
    """Возвращает tenant_id активного контекста (филиала) пользователя."""
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def must_network_id(request: Request) -> int:
    """
    Возвращает id корня сети (головного тенанта).
    Клиенты, бонусы и настройки лояльности общие на сеть и хранятся на корне.
    """
    u = getattr(request.state, "user", None) or {}
    nid = u.get("network_id") or u.get("tenant_id")
    if not nid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(nid)


def network_tenant_ids(db: Session, network_id: int) -> list[int]:
    """Все tenant_id сети: корень + филиалы."""
    ids = [int(network_id)]
    children = db.query(Tenant.id).filter(Tenant.parent_tenant_id == int(network_id)).all()
    ids.extend(int(c[0]) for c in children)
    return ids


def get_tenant_ids_for_user(request: Request, db: Session) -> list[int]:
    """
    Возвращает список tenant_id, доступных пользователю.
    Если пользователь owner головного тенанта — видит все филиалы группы.
    Иначе — только свой тенант.
    """
    u = getattr(request.state, "user", None) or {}
    tenant_id = int(u.get("tenant_id") or 0)
    role = u.get("role", "")

    if role == "owner":
        # Проверяем, головной ли это тенант (parent_tenant_id IS NULL)
        tenant = db.get(Tenant, tenant_id)
        if tenant and tenant.parent_tenant_id is None:
            # Головной тенант — возвращаем все филиалы группы + себя
            group_ids = [tenant_id]
            children = db.query(Tenant).filter(Tenant.parent_tenant_id == tenant_id).all()
            for child in children:
                group_ids.append(child.id)
            return group_ids

    # Для всех остальных — только свой тенант
    return [tenant_id]


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    role = u.get("role", "")
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Access denied. Required roles: {allowed}")
    return u
