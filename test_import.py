#!/usr/bin/env python3
try:
    from main import app
    print("✓ main.py imported successfully")
    print(f"✓ app has {len(app.routes)} routes")
    
    # List API routes
    api_routes = [r.path for r in app.routes if r.path.startswith('/api/')]
    print(f"✓ {len(api_routes)} API routes found:")
    for path in sorted(api_routes):
        print(f"    - {path}")
        
except Exception as e:
    print(f"✗ Error importing main: {e}")
    import traceback
    traceback.print_exc()
