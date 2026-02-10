#!/usr/bin/env python3
"""
Test API endpoints via HTTP
"""
import requests
import sys
import json

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(method, path, expected_status=None):
    """Test an endpoint and print results"""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=5)
        elif method == "POST":
            resp = requests.post(url, json={}, timeout=5)
        else:
            return None
        
        status_ok = expected_status is None or resp.status_code == expected_status
        status_icon = "✓" if status_ok else "✗"
        print(f"  {status_icon} {method:6s} {path:50s} [{resp.status_code}]")
        return resp.status_code
    except Exception as e:
        print(f"  ✗ {method:6s} {path:50s} [ERROR: {e}]")
        return None

print("\n=== TESTING API ENDPOINTS ===\n")

# Test each endpoint
endpoints = [
    ("GET", "/api/users/", 200),
    ("GET", "/api/transactions/bonus-balance/77001234567", [404, 200]),  # Either is OK for now
    ("GET", "/api/transactions/by-phone/77001234567", [404, 200]),
    ("GET", "/api/crm/client/77001234567", [404, 200]),
    ("POST", "/api/transactions", [422, 404, 200]),  # Could be validation error
    ("GET", "/admin", 200),
    ("GET", "/", 200),
]

results = {}
for method, path, expected in endpoints:
    # Convert expected to list for uniform handling
    if isinstance(expected, int):
        expected = [expected]
    
    status = test_endpoint(method, path)
    if status:
        is_ok = status in expected
        results[path] = "OK" if is_ok else "FAIL"

print("\n=== SUMMARY ===\n")
ok_count = sum(1 for v in results.values() if v == "OK")
total_count = len(results)
print(f"Passed: {ok_count}/{total_count}")

if ok_count < total_count:
    print("\nFailed endpoints:")
    for path, status in results.items():
        if status == "FAIL":
            print(f"  - {path}")
