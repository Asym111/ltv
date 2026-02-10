from decimal import Decimal, ROUND_HALF_UP

TIERS = {
    "Bronze": Decimal("0.01"),
    "Silver": Decimal("0.02"),
    "Gold": Decimal("0.03"),
}


def calc_bonus(amount: Decimal, tier: str) -> Decimal:
    rate = TIERS.get(tier, TIERS["Bronze"])
    bonus = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return bonus
