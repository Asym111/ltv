#!/usr/bin/env python
"""Quick verification that imports work"""
try:
    from main import app
    from app.core.tier_rules import RULES, tier_from_total
    from app.services.tier import recompute_user_tier
    print("✅ All imports successful")
    print(f"✅ Tier Rules: {RULES}")
    routes = [r.path for r in app.router.routes]
    print(f"✅ Routes count: {len(routes)}")
    print("✅ Application is ready!")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
