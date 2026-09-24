"""
Final report - Nera customer experience audit
"""
import sys
sys.path.insert(0, '/root/NekoSalesAI/backend')
from app.main import app
from fastapi.testclient import TestClient
import json

client = TestClient(app)

# Quick smoke test of all endpoints
endpoints = [
    ("GET", "/"),
    ("GET", "/build"),
    ("GET", "/dashboard"),
    ("GET", "/login"),
    ("GET", "/signup"),
    ("GET", "/pricing"),
    ("GET", "/products"),
    ("GET", "/workforce"),
    ("GET", "/demo"),
    ("GET", "/trust"),
    ("GET", "/pricing"),
    ("GET", "/api/v1/pricing/options"),
    ("POST", "/api/v1/pricing/quote"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
]

print("\n" + "=" * 60)
print("ENDPOINT SMOKE TEST")
print("=" * 60)

for item in endpoints:
    method, path = item
    try:
        if method == "GET":
            r = client.get(path)
        elif method == "POST":
            if "quote" in path:
                r = client.post(path, json={
                    "product_type": "sales_agent",
                    "channels": ["web"],
                    "monthly_conversations": 500,
                    "integrations": ["crm"],
                    "languages": ["en"]
                })
            elif "register" in path:
                r = client.post(path, json={
                    "email": "audit.test@example.com",
                    "password": "TestPass123!",
                    "full_name": "Audit Bot 2026",
                    "company_name": "Audit Co"
                })
            elif "login" in path:
                r = client.post(path, json={
                    "email": "audit.test@example.com",
                    "password": "TestPass123!"
                })
            else:
                r = client.post(path, json={})
        status = r.status_code
        print(f"  {method:6} {path:40} {status}")
    except Exception as e:
        print(f"  {method:6} {path:40} ERROR: {str(e)[:40]}")

print("\n" + "=" * 60)
