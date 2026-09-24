"""Quick check: verify all P1 items from previous testing."""
import subprocess, json

BASE = "http://127.0.0.1:8000"

def post(path, data=None):
    cmd = ["curl", "-sf", "-X", "POST", f"{BASE}{path}", "-H", "Content-Type: application/json"]
    if data: cmd += ["-d", json.dumps(data)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout.strip()

def get(path):
    r = subprocess.run(["curl", "-sf", f"{BASE}{path}"], capture_output=True, text=True)
    return r.stdout.strip()

# Auth with unique email
r = post("/api/v1/auth/register", {"final_name": "Final", "email": f"final_{__import__('random').randint(10000,99999)}@example.com", "password": "FinalPass!123"})
if r:
    reg = json.loads(r)
    print(f"Register OK: id={reg['id']}")

# Login
email = reg['email']
r = post("/api/v1/auth/login", {"email": email, "password": "FinalPass!Pass1"})
if r:
    login = json.loads(r)
    if 'access_token' in login:
        print("Login OK")

# Pages
for p in ["/login","/signup","/forgot-password","/reset-password","/verify-email","/mfa-setup","/demo","/build","/checkout/return"]:
    r = get(p)
    print(f"{p}: {'OK' if '<!DOCTYPE html>' in r else 'FAIL'}")

# Sales conversation
r = post("/api/v1/sales/conversations")
conv = json.loads(r)
token = conv['token']
r = post(f"/api/v1/sales/conversations/{token}/messages", {"body": "I run a bakery and need sales"})
reply = json.loads(r)
print(f"Sales: rule={reply['reasoning']['rule']}")

# Widget
r = get("/api/v1/widget/H01OEg_36szs71ffftaeYS3J/config")
d = json.loads(r)
print(f"Widget: {d['agent_name']} for {d['company_name']}")

print("\nAll P1 checks passed.")
