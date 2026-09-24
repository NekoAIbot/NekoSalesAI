"""Paystack checkout test."""
import urllib.request
import json

BASE = "http://127.0.0.1:8000"

# Create a quote
payload = {"products": ["sales_agent"], "channels": ["web"], "monthly_conversations": 500}
req = urllib.request.Request(BASE + "/api/v1/pricing/quote",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
quote = json.loads(resp.read())
ref = quote["reference"]
print("Quote:", ref, "=", quote["display_total"])

# Create checkout order
payload2 = {"quote_reference": ref, "email": "e2e_test@example.com", "name": "E2E", "company": "Test"}
req2 = urllib.request.Request(BASE + "/api/v1/checkout/orders",
    data=json.dumps(payload2).encode(),
    headers={"Content-Type": "application/json"})
try:
    resp2 = urllib.request.urlopen(req2)
    order = json.loads(resp2.read())
    print("Checkout URL:", order.get("checkout_url", "N/A"))
    print("Order ref:", order.get("paystack_reference", "N/A"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, ":", e.read()[:300])
