from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.roles import TRANSACTION_ROLES
from app.models.task import Task

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── Schemas ────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: int
    text: str
    assignee: Optional[str] = None
    done: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    assignee: Optional[str] = Field(default=None, max_length=120)


class TaskUpdate(BaseModel):
    done: Optional[bool] = None
    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    assignee: Optional[str] = Field(default=None, max_length=120)


# ── Helpers ────────────────────────────────────────────────

def must_tenant_id(request: Request) -> int:
    u = getattr(request.state, "user", None) or {}
    tid = u.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(tid)


def require_role(request: Request, *allowed: str):
    u = getattr(request.state, "user", None) or {}
    if u.get("role") not in allowed:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return u


# ── Endpoints ──────────────────────────────────────────────

@router.get("/", response_model=list[TaskOut])
def list_tasks(request: Request, db: Session = Depends(get_db)):
    require_role(request, *TRANSACTION_ROLES)
    tenant_id = must_tenant_id(request)
    tasks = (
        db.query(Task)
        .filter(Task.tenant_id == tenant_id)
        .order_by(Task.created_at.desc())
        .all()
    )
    return tasks


@router.post("/", response_model=TaskOut)
def create_task(payload: TaskCreate, request: Request, db: Session = Depends(get_db)):
    require_role(request, *TRANSACTION_ROLES)
    u = must_tenant_id(request)
    current_user = getattr(request.state, "user", None) or {}
    task = Task(
        tenant_id=u,
        text=payload.text.strip(),
        assignee=(payload.assignee or "").strip() or None,
        done=False,
        created_by_id=current_user.get("id"),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, request: Request, db: Session = Depends(get_db)):
    require_role(request, *TRANSACTION_ROLES)
    tenant_id = must_tenant_id(request)
    task = db.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if payload.done is not None:
        task.done = payload.done
    if payload.text is not None:
        task.text = payload.text.strip()
    if payload.assignee is not None:
        task.assignee = payload.assignee.strip() or None
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}")
def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, *TRANSACTION_ROLES)
    tenant_id = must_tenant_id(request)
    task = db.query(Task).filter(Task.id == task_id, Task.tenant_id == tenant_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"ok": True}
