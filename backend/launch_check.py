"""Final launch readiness check."""
import subprocess, json, time
from app.config.settings import settings

BASE = "http://127.0.0.1:8000"

print("=" * 70)
print("FINAL LAUNCH READINESS CHECK")
print("=" * 70)

# 1. Brevo SMTP
print("\n[1] BREVO SMTP")
print(f"  MAIL_BACKEND: {settings.MAIL_BACKEND}")
print(f"  SMTP_HOST: {settings.SMTP_HOST}")
print(f"  SMTP_PORT: {settings.SMTP_PORT}")
print(f"  SMTP_USERNAME set: {bool(settings.SMTP_USERNAME)}")
print(f"  SMTP_PASSWORD set: {bool(settings.SMTP_PASSWORD)}")
print(f"  BREVO_API_KEY set: {bool(settings.BREVO_API_KEY)}")

# 2. Public URL
print("\n[2] PUBLIC BASE URL")
print(f"  PUBLIC_BASE_URL: {settings.PUBLIC_BASE_URL}")

# 3. Paystack
print("\n[3] PAYSTACK")
print(f"  Secret key set: {bool(settings.PAYSTACK_SECRET_KEY)}")
print(f"  Public key set: {bool(settings.PAYSTACK_PUBLIC_KEY)}")
print(f"  Live mode: {settings.paystack_is_live}")

# 4. Telegram
print("\n[4] TELEGRAM")
r = subprocess.run(["bash", "-lc", "cd /root/NekoSalesAI/backend && ./nera.sh --status 2>&1 | head -3"],
                   capture_output=True, text=True)
print(f"  {r.stdout.strip()}")

# 5. Sales quote
print("\n[5] SALES QUOTE")
cmd = ["curl", "-sf", "-X", "POST", f"{BASE}/api/v1/pricing/quote", "-H", "Content-Type: application/json",
       "-d", json.dumps({"products":["sales_agent"],"channels":["web"],"monthly_conversations":500})]
r = subprocess.run(cmd, capture_output=True, text=True)
d = json.loads(r.stdout)
print(f"  Quote: {d['display_total']}")

# 6. Widget
print("\n[6] CUSTOMER WIDGET")
r = subprocess.run(["curl", "-sf", f"{BASE}/api/v1/widget/H01OEg_36szs71ffftaeYS3J/config"],
                   capture_output=True, text=True)
d = json.loads(r.stdout)
print(f"  Widget: {d['agent_name']} for {d['company_name']}")

print("\n" + "=" * 70)
print("STATUS")
print("=" * 70)

creds_ok = bool(settings.SMTP_USERNAME and settings.SMTP_PASSWORD)
public_ok = "127.0.0.1" not in settings.PUBLIC_BASE_URL
paystack_ok = bool(settings.PAYSTACK_SECRET_KEY)

print(f"Brevo SMTP: {'READY' if creds_ok else 'BLOCKED - needs credentials'}")
print(f"Public URL: {'OK' if public_ok else 'BLOCKED - localhost'}")
print(f"Paystack: {'OK' if paystack_ok else 'BLOCKED - no keys'}")
print(f"Telegram: {'Running' if 'Nera is answering' in r.stdout else 'Stopped'}")
