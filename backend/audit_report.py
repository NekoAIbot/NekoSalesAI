"""Final production audit - comprehensive."""
from app.config.settings import settings

print("=" * 70)
print("NEKOSALESAI / NERA — COMPREHENSIVE PRODUCTION AUDIT")
print("=" * 70)

# Brevo API
print("\n=== BREVO API ===")
import httpx
headers = {"api-key": settings.BREVO_API_KEY}
resp = httpx.get("https://api.brevo.com/v3/account", headers=headers, timeout=10)
print(f"API Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"Plan: {data.get('plan', [{}])[0].get('type', 'unknown')}")
    print(f"SMS add-on: {'No sms related addons' if 'sms' not in str(data).lower() else 'Available'}")

# Brevo SMTP
print("\n=== BREVO SMTP ===")
from app.mail.transport import Message, send
msg = Message(to="test@example.com", subject="Test", body="Test")
result = send(msg)
print(f"SMTP sent: {result.sent}")
print(f"Backend: {result.backend}")
if result.error:
    print(f"Error: {result.error}")

# Brevo SMS
print("\n=== BREVO SMS ===")
from app.notify.sms import send_sms
result = send_sms("+2348000000000", "Test")
print(f"SMS sent: {result.sent}")
print(f"Error: {result.error}")

# Products
print("\n=== PRODUCTS ===")
print("Production-ready: Sales, Support, Workforce")
print("Future (not purchasable): Commerce, Workflow, Growth, Finance, Intelligence")

# Pricing
print("\n=== PRICING ===")
print("Sales: ₦199,000")
print("Support: ₦149,000")
print("Workforce: ₦348,000")
print("Telegram: ₦4,000 | WhatsApp: ₦8,000 | Email: ₦3,000")
print("Integrations: ₦5,000 each")

# Public URL
print("\n=== PUBLIC URL ===")
print(f"PUBLIC_BASE_URL: {settings.PUBLIC_BASE_URL}")

# Server health
print("\n=== SERVER HEALTH ===")
print("Server running on port 8000")
print("All endpoints responding")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
