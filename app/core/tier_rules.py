from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TierRules:
    # Пороги по total_spent (KZT)
    silver_from: Decimal = Decimal("300000")   # от 300k → Silver
    gold_from: Decimal = Decimal("1000000")    # от 1M → Gold


RULES = TierRules()


def tier_from_total(total_spent: Decimal) -> str:
    if total_spent >= RULES.gold_from:
        return "Gold"
    if total_spent >= RULES.silver_from:
        return "Silver"
    return "Bronze"
