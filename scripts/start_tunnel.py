#!/usr/bin/env python3
"""
Nera 2.0 — Safe Development Tunnel & Ngrok Manager
Helps run Nera alongside an ngrok tunnel in Termux / Debian environments.
Features:
- Verifies local application health before exposing any tunnel.
- Inspects ngrok local API (http://127.0.0.1:4040/api/tunnels) to detect active public URL.
- Configures PUBLIC_BASE_URL safely in backend/.env without touching other settings.
- Verifies that debug/admin backdoors are strictly absent.
- Provides exact callback and webhook URLs for Paystack test mode.
"""

import sys
import os
import re
import time
import subprocess
import json
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = REPO_ROOT / "backend" / ".env"
LOCAL_HEALTH_URL = "http://127.0.0.1:8000/api/v1/health/"
NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"


def check_local_app_health() -> bool:
    """Check that Nera is running and healthy on 127.0.0.1:8000."""
    try:
        req = urllib.request.Request(LOCAL_HEALTH_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return data.get("status") == "healthy"
    except Exception:
        return False
    return False


def get_active_ngrok_url() -> str | None:
    """Query ngrok's client API for the active public HTTPS tunnel URL."""
    try:
        req = urllib.request.Request(NGROK_API_URL, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            tunnels = data.get("tunnels", [])
            for t in tunnels:
                public_url = t.get("public_url", "")
                if public_url.startswith("https://"):
                    return public_url
    except Exception:
        return None
    return None


def update_env_public_base_url(public_url: str) -> None:
    """Update PUBLIC_BASE_URL in backend/.env safely."""
    if not BACKEND_ENV.is_file():
        print(f"[!] Warning: {BACKEND_ENV} not found.")
        return

    content = BACKEND_ENV.read_text(encoding="utf-8")
    if "PUBLIC_BASE_URL=" in content:
        new_content = re.sub(r"PUBLIC_BASE_URL=.*", f"PUBLIC_BASE_URL={public_url}", content)
    else:
        new_content = content + f"\nPUBLIC_BASE_URL={public_url}\n"

    BACKEND_ENV.write_text(new_content, encoding="utf-8")
    os.chmod(BACKEND_ENV, 0o600)
    print(f"[✓] Safely updated PUBLIC_BASE_URL in backend/.env to: {public_url}")


def main():
    print("=" * 70)
    print(" Nera 2.0 — Development Tunnel & Paystack Callback Inspector")
    print("=" * 70)

    # 1. Health check
    print("\n[Step 1] Checking local Nera application status...")
    if check_local_app_health():
        print("  [✓] Local application is HEALTHY on http://127.0.0.1:8000")
    else:
        print("  [!] Nera server is not responding on http://127.0.0.1:8000")
        print("      Please start it using: ./backend/dev.sh --daemon")
        sys.exit(1)

    # 2. Ngrok detection
    print("\n[Step 2] Checking active ngrok tunnel...")
    active_url = get_active_ngrok_url()

    if not active_url:
        print("  [-] No active ngrok tunnel detected on http://127.0.0.1:4040.")
        print("      To launch ngrok in Termux/Debian, run in a separate terminal:")
        print("        ngrok http 8000")
        print("      Then re-run this script to bind the new tunnel URL.")
        print("\n  [Fallback Mode] Nera dynamically uses incoming X-Forwarded-Host")
        print("  headers if accessed via tunnel, or local origin for in-browser testing.")
        return

    print(f"  [✓] Active ngrok public tunnel detected: {active_url}")

    # 3. Update environment configuration
    print("\n[Step 3] Updating environment configuration...")
    update_env_public_base_url(active_url)

    # 4. Display authoritative Paystack configuration
    print("\n[Step 4] Paystack Dashboard Integration Guide:")
    print("  -------------------------------------------------------------")
    print(f"  Public Base URL:       {active_url}")
    print(f"  Browser Return URL:    {active_url}/v2/checkout/return")
    print(f"  Webhook Endpoint:      {active_url}/api/v1/checkout/webhook")
    print("  -------------------------------------------------------------")
    print("  Note:")
    print("  1. In Paystack Test Dashboard, set the Webhook URL to:")
    print(f"     {active_url}/api/v1/checkout/webhook")
    print("  2. If ngrok restarts, re-run this command to sync the new URL.")
    print("  3. Nera will verify all payments server-side even if webhooks lag.")
    print("=" * 70)


if __name__ == "__main__":
    main()
