from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LoyaltyRules:
    bronze_rate: Decimal = Decimal("0.01")
    silver_rate: Decimal = Decimal("0.02")
    gold_rate: Decimal = Decimal("0.03")
    max_redeem_percent: Decimal = Decimal("0.30")


RULES = LoyaltyRules()
