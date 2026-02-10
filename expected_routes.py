#!/usr/bin/env python3
"""
Quick test of API endpoints
"""
import sys
import json

# Avoid importing main (which would start uvicorn)
# Instead, we'll just print expected routes

expected_routes = {
    "/api/users/": "GET",
    "/api/users/{user_id}": "GET",
    "/api/transactions": "POST",
    "/api/transactions/bonus-balance/{user_phone}": "GET",
    "/api/transactions/by-phone/{user_phone}": "GET",
    "/api/crm/client/{phone}": "GET",
}

print("Expected API Routes:")
print("=" * 60)
for path, method in expected_routes.items():
    print(f"  {method:6s} {path}")

print("\nTo verify these are registered in main.py:")
print("1. Open http://127.0.0.1:8000/docs in browser")
print("2. Check if all routes above are listed")
print("3. Try a GET /api/users/ call first")
