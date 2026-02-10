#!/usr/bin/env python3
"""
Тестируем импорт роутеров и проверяем, загружаются ли они в FastAPI
"""
import sys
import os

# Set up path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Step 1: Importing main app...")
try:
    from main import app
    print(f"✓ Main app imported. Total routes: {len(app.routes)}")
except Exception as e:
    print(f"✗ Failed to import main: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nStep 2: Checking API routes...")
api_routes = []
for route in app.routes:
    if hasattr(route, 'path'):
        if route.path.startswith('/api/'):
            api_routes.append(route)
            methods = getattr(route, 'methods', set())
            methods_str = ', '.join(sorted(methods)) if methods else 'N/A'
            print(f"  ✓ {route.path:50s} [{methods_str}]")

print(f"\nTotal API routes found: {len(api_routes)}")

print("\nStep 3: Checking specific endpoints...")
expected = [
    "/api/crm/client/{phone}",
    "/api/transactions",
    "/api/transactions/by-phone/{user_phone}",
]

for expected_path in expected:
    found = any(r.path == expected_path for r in api_routes)
    status = "✓" if found else "✗"
    print(f"  {status} {expected_path}")

print("\nDone!")
