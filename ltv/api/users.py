from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.phone == payload.phone)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="User with this phone already exists")

    user = User(
        phone=payload.phone,
        full_name=payload.full_name,
        is_staff=payload.is_staff,
        loyalty_tier=payload.loyalty_tier,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.id.desc())).scalars().all()
    return list(users)
