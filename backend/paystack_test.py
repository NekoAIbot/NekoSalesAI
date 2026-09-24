"""Paystack checkout E2E test."""
import urllib.request, json

BASE = "http://127.0.0.1:8000"

# Create quote
req = urllib.request.Request(
    f"{BASE}/api/v1/pricing/quote",
    data=json.dumps({"products":["sales_agent"],"channels":["web"],"monthly_conversations":500}).encode(),
    headers={"Content-Type": "application/json"}
)
resp = urllib.request.urlopen(req)
quote = json.loads(resp.read())
ref = quote["reference"]
print(f"Quote: {ref} = {quote['display_total']}")

# Create checkout order
req2 = urllib.request.Request(
    f"{BASE}/api/v1/checkout/orders",
    data=json.dumps({
        "quote_reference": ref,
        "email": "e2e_test@example.com",
        "name": "E2E",
        "company": "Test"
    }).encode(),
    headers={"Content-Type": "application/json"}
)
try:
    resp2 = urllib.request.urlopen(req2)
    order = json.loads(resp2.read())
    print(f"Checkout URL: {order.get('checkout_url', 'N/A')}")
    print(f"Order reference: {order.get('paystack_reference', 'N/A')}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read()[:300]}")
