from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if s.startswith("+"):
        s = s[1:]
    digits = "".join(ch for ch in s if ch.isdigit())
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) > 11:
        digits = digits[-11:]
    return digits


@router.get("/", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    users = db.query(User).order_by(User.id.desc()).all()
    return [UserOut.model_validate(u) for u in users]


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserOut:
    phone = normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="Invalid phone")

    exists = db.query(User).filter(User.phone == phone).first()
    if exists:
        raise HTTPException(status_code=400, detail="Phone already exists")

    user = User(
        phone=phone,
        full_name=payload.full_name,
        birth_date=payload.birth_date,
        tier=payload.tier or "Bronze",
        bonus_balance=int(payload.bonus_balance or 0),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> UserOut:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.birth_date is not None:
        user.birth_date = payload.birth_date
    if payload.tier is not None:
        user.tier = payload.tier
    if payload.bonus_balance is not None:
        user.bonus_balance = int(payload.bonus_balance)

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
