from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.core.tier_rules import tier_from_total
from app.models.transaction import Transaction
from app.models.user import User


def recompute_user_tier(db: Session, user: User) -> str:
    total_spent = db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(Transaction.user_id == user.id)
    ).scalar_one()

    total_spent_dec = Decimal(str(total_spent))
    new_tier = tier_from_total(total_spent_dec)

    if user.loyalty_tier != new_tier:
        user.loyalty_tier = new_tier
        db.add(user)

    return new_tier
