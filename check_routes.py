#!/usr/bin/env python
import sys
sys.path.insert(0, '.')

from main import app

print("\n=== REGISTERED ROUTES ===\n")
for route in sorted(app.routes, key=lambda r: r.path):
    if hasattr(route, 'methods'):
        methods = ', '.join(sorted(route.methods))
        print(f"{route.path:50s} {methods}")
    else:
        print(f"{route.path:50s}")

print("\n=== API ROUTES ANALYSIS ===\n")
api_routes = [r for r in app.routes if r.path.startswith('/api/')]
for route in sorted(api_routes, key=lambda r: r.path):
    if hasattr(route, 'methods'):
        methods = ', '.join(sorted(route.methods))
        print(f"✓ {route.path:45s} {methods}")
    else:
        print(f"✓ {route.path:45s}")

print(f"\nTotal API routes: {len(api_routes)}")
