import sys
sys.path.insert(0, '.')

# Check imports
try:
    from app.api.crm import router as crm_router
    print("✓ app.api.crm imported successfully")
    print(f"  Routes in crm_router: {[r.path for r in crm_router.routes]}")
except Exception as e:
    print(f"✗ Failed to import crm: {e}")

try:
    from app.api.transactions import router as tx_router
    print("✓ app.api.transactions imported successfully")
    print(f"  Routes in tx_router: {[r.path for r in tx_router.routes]}")
except Exception as e:
    print(f"✗ Failed to import transactions: {e}")

try:
    from app.api.users import router as users_router
    print("✓ app.api.users imported successfully")
    print(f"  Routes in users_router: {[r.path for r in users_router.routes]}")
except Exception as e:
    print(f"✗ Failed to import users: {e}")

print("\n=== APP ROUTES ===")
from main import app
print(f"Total routes: {len(app.routes)}")

api_count = 0
for r in app.routes:
    if r.path.startswith('/api/'):
        api_count += 1
        methods = getattr(r, 'methods', None)
        if methods:
            print(f"  {r.path:45s} {methods}")
        else:
            print(f"  {r.path:45s}")

print(f"\nAPI Routes found: {api_count}")
