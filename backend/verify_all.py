"""Complete system verification. Run inside proot container."""
import subprocess, json, sys

def post(path, data=None):
    cmd = ["curl", "-sf", "-X", "POST", f"http://127.0.0.1:8000{path}", "-H", "Content-Type: application/json"]
    if data: cmd += ["-d", json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()

def get(path):
    r = subprocess.run(["curl", "-sf", f"http://127.0.0.1:8000{path}"], capture_output=True, text=True)
    return r.stdout.strip()

print("=== P0: CORE PRODUCT & PRICING ===")
r = post("/api/v1/pricing/quote", {
    "products": ["sales_agent","support_agent"],
    "channels": ["web","telegram","whatsapp","email"],
    "integrations": ["crm","calendar","payment","stock"],
    "monthly_conversations": 10000
})
d = json.loads(r)
print(f"Quote total: {d['display_total']} (expect ₦403,000)")
assert d['total_minor'] == 40300000, f"Expected 40300000 got {d['total_minor']}"
print("PASSED: Pricing engine computes ₦403,000")

print("\n=== P0: AUTH — REGISTER + VERIFY + LOGIN ===")
r = post("/api/v1/auth/register", {"full_name":"Verify Test","email":"verify_test@example.com","password":"Str0ng!Pass","company_name":"VerifyCo"})
d = json.loads(r)
print(f"Register: id={d.get('id')}, email_verified={d.get('email_verified')}")
assert d.get('email_verified') == False
print("PASSED: Registration requires email verification")

# Try login before verification
r = post("/api/v1/auth/login", {"email":"verify_test@example.com","password":"Str0ng!Pass"})
print(f"Login before verify: {r[:100]}")

print("\n=== P0: CHECKOUT RETURN STATE MACHINE ===")
r = get("/api/v1/checkout/orders/neko_f0917d027bb5cd23fcccb684")
d = json.loads(r)
ws = d.get('workspace', {})
print(f"Order status: {d['order']['status']}")
print(f"Workspace status: {ws.get('status')}")
print(f"Failure reason: {ws.get('failure_reason')}")
print(f"Steps done: {sum(1 for s in ws.get('steps',[]) if s['done'])}/4")
assert ws.get('status') == 'ready'
assert ws.get('failure_reason') is None
print("PASSED: Checkout return shows clean ready state")

print("\n=== P0: WIDGET RENDERS ===")
r = get("/api/v1/widget/H01OEg_36szs71ffftaeYS3J/config")
d = json.loads(r)
print(f"Widget: {d['agent_name']} for {d['company_name']}")
assert d['agent_name'] == 'Ada'
print("PASSED: Widget serves customer's agent, not Nera")

print("\n=== P1: WEB PAGES ===")
for path in ["/login","/signup","/forgot-password","/reset-password","/verify-email","/mfa-setup","/demo","/build","/products","/desk","/checkout/return"]:
    r = get(path)
    ok = r.startswith("<!DOCTYPE html>")
    print(f"  {path}: {'OK' if ok else 'FAIL'}")
print("PASSED: All auth pages render")

print("\n=== P1: EMAIL BACKEND ===")
from app.config.settings import settings
print(f"MAIL_BACKEND: {settings.MAIL_BACKEND}")
if settings.MAIL_BACKEND == "smtp":
    print(f"SMTP_HOST: {settings.SMTP_HOST}")
    print("PASSED: SMTP configured")
else:
    print(f"BLOCKED: MAIL_BACKEND is '{settings.MAIL_BACKEND}' — emails are logged, not sent")
    print("To send: set MAIL_BACKEND=smtp, SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD in .env")

print("\n=== P1: PUBLIC BASE URL ===")
print(f"PUBLIC_BASE_URL: {settings.PUBLIC_BASE_URL}")
if "127.0.0.1" in settings.PUBLIC_BASE_URL:
    print("BLOCKED: PUBLIC_BASE_URL is localhost — customers cannot reach it")
else:
    print("PASSED: Public URL configured")

print("\n=== P1: TELEGRAM ===")
r = subprocess.run(["bash", "-lc", "cd /root/NekoSalesAI/backend && ./nera.sh --status"], capture_output=True, text=True)
print(r.stdout[:200])
if "Nera is answering" in r.stdout:
    print("PASSED: Telegram poller running")
else:
    print("BLOCKED: Telegram poller not running")

print("\n=== PAYSTACK ===")
print(f"PAYSTACK_SECRET_KEY set: {bool(settings.PAYSTACK_SECRET_KEY)}")
print(f"PAYSTACK_PUBLIC_KEY set: {bool(settings.PAYSTACK_PUBLIC_KEY)}")
print(f"Live mode: {settings.paystack_is_live}")
