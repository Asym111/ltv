#!/usr/bin/env python3
"""
Comprehensive diagnostics of LTV system
"""
import sys
sys.path.insert(0, '.')

print("\n" + "="*70)
print("LTV SYSTEM DIAGNOSTICS".center(70))
print("="*70 + "\n")

# 1. Import main
print("[1/4] Checking main.py import...")
try:
    from main import app
    print("    ✓ main.py imported successfully")
except Exception as e:
    print(f"    ✗ Failed: {e}")
    sys.exit(1)

# 2. Check database
print("\n[2/4] Checking database...")
try:
    from app.core.database import engine, Base
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    if "users" in tables:
        print("    ✓ Database tables created:")
        for table in sorted(tables):
            print(f"        - {table}")
    else:
        print("    ✗ No 'users' table found. Creating tables...")
        Base.metadata.create_all(bind=engine)
        print("    ✓ Tables created successfully")
except Exception as e:
    print(f"    ✗ Database check failed: {e}")

# 3. Check routes
print("\n[3/4] Checking API routes...")
try:
    api_routes = sorted([r.path for r in app.routes if r.path.startswith('/api/')])
    web_routes = sorted([r.path for r in app.routes if r.path.startswith('/admin')])
    
    print(f"    ✓ Found {len(api_routes)} API routes:")
    for route in api_routes:
        print(f"        - {route}")
    
    print(f"\n    ✓ Found {len(web_routes)} Web UI routes:")
    for route in web_routes:
        print(f"        - {route}")
        
    # Check critical endpoints
    critical = [
        '/api/transactions',
        '/api/transactions/by-phone/{user_phone}',
        '/api/crm/client/{phone}',
        '/api/users/',
    ]
    
    missing = [r for r in critical if r not in api_routes]
    if missing:
        print(f"\n    ✗ Missing critical routes: {missing}")
    else:
        print(f"\n    ✓ All critical routes registered")
        
except Exception as e:
    print(f"    ✗ Route check failed: {e}")

# 4. Check static files & templates
print("\n[4/4] Checking static files and templates...")
try:
    import os
    
    static_files = os.path.exists('static')
    templates_files = os.path.exists('templates')
    
    print(f"    {'✓' if static_files else '✗'} static/ directory: {'OK' if static_files else 'MISSING'}")
    print(f"    {'✓' if templates_files else '✗'} templates/ directory: {'OK' if templates_files else 'MISSING'}")
    
    if static_files:
        static_list = os.listdir('static')
        print(f"        - Contains: {', '.join(static_list)}")
    
    if templates_files:
        template_list = os.listdir('templates')
        print(f"        - Contains: {', '.join(template_list)}")
        
except Exception as e:
    print(f"    ✗ File check failed: {e}")

print("\n" + "="*70)
print("DIAGNOSTICS COMPLETE".center(70))
print("="*70 + "\n")

print("Next steps:")
print("  1. Start the server: python -m uvicorn main:app --port 8000")
print("  2. Visit http://127.0.0.1:8000/admin - Admin UI")
print("  3. Visit http://127.0.0.1:8000/docs - Swagger API Docs")
print("")
