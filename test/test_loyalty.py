"""
Unit-тесты для loyalty_engine: calc_earn, redeem_cap.
"""
import pytest
from datetime import datetime, timedelta, timezone

from app.services.loyalty_engine import calc_earn, redeem_cap


class MockSettings:
    def __init__(self, **kwargs):
        self.tiers_json = kwargs.get("tiers_json", [])
        self.earn_bronze_percent = kwargs.get("earn_bronze_percent", 3)
        self.earn_silver_percent = kwargs.get("earn_silver_percent", 5)
        self.earn_gold_percent = kwargs.get("earn_gold_percent", 7)
        self.redeem_max_percent = kwargs.get("redeem_max_percent", 30)
        self.silver_threshold = kwargs.get("silver_threshold", 5000)
        self.gold_threshold = kwargs.get("gold_threshold", 20000)


class TestCalcEarn:

    def test_zero_amount(self):
        s = MockSettings()
        assert calc_earn(0, "Bronze", s) == 0

    def test_negative_amount(self):
        s = MockSettings()
        assert calc_earn(-1000, "Bronze", s) == 0

    def test_bronze(self):
        s = MockSettings(earn_bronze_percent=3, silver_threshold=5000)
        assert calc_earn(4000, "Bronze", s) == 120

    def test_silver(self):
        s = MockSettings(earn_silver_percent=5, silver_threshold=5000, gold_threshold=20000)
        assert calc_earn(10000, "Bronze", s) == 500

    def test_gold(self):
        s = MockSettings(earn_gold_percent=7, silver_threshold=5000, gold_threshold=20000)
        assert calc_earn(25000, "Bronze", s) == 1750

    def test_tiers_json(self):
        tiers = [
            {"name": "Bronze", "bonus_percent": 3},
            {"name": "Silver", "bonus_percent": 5},
            {"name": "Gold", "bonus_percent": 7},
        ]
        s = MockSettings(tiers_json=tiers)
        assert calc_earn(10000, "Silver", s) == 500

    def test_rounding(self):
        s = MockSettings(earn_bronze_percent=3)
        assert calc_earn(333, "Bronze", s) == 9


class TestRedeemCap:

    def test_zero(self):
        s = MockSettings(redeem_max_percent=30)
        assert redeem_cap(0, s) == 0

    def test_30_percent(self):
        s = MockSettings(redeem_max_percent=30)
        assert redeem_cap(10000, s) == 3000

    def test_100_percent(self):
        s = MockSettings(redeem_max_percent=100)
        assert redeem_cap(5000, s) == 5000

    def test_over_100_clamped(self):
        s = MockSettings(redeem_max_percent=150)
        assert redeem_cap(1000, s) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])