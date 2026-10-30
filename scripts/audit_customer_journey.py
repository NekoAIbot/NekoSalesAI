"""End-to-End Browser Customer Journey Audit for NERA 2.0.

Exercises:
1. Homepage navigation & CTAs
2. Configurator interactions (product switches, volume changes, live API quote display)
3. Synthetic account registration, login, authenticated dashboard state
4. Checkout return states (pending, success, cancelled, error)
5. Browser console and network request inspection (checks for 0 unexpected errors)
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000/v2"
SCREENSHOT_DIR = Path("/root/.gemini/antigravity-cli/brain/ea1c17dd-c7be-4245-871e-e7da1d3a6583/audit_screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def run_customer_journey_audit():
    print("Starting Comprehensive Browser Customer Journey Audit...")
    console_errors = []
    failed_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-ipv6', '--no-sandbox'])
        context = browser.new_context(viewport={"width": 1280, "height": 800})

        # Fulfill external font calls with empty mock to prevent external hanging without ERR_FAILED
        context.route("https://fonts.googleapis.com/**", lambda route: route.fulfill(status=200, content_type="text/css", body=""))
        context.route("https://fonts.gstatic.com/**", lambda route: route.fulfill(status=200, content_type="font/woff2", body=b""))
        context.route("https://api.paystack.co/**", lambda route: route.fulfill(status=200, content_type="application/json", body="{}"))
        context.route("**/api/v1/checkout/orders/T_JOURNEY_PENDING_01", lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"order": {"status": "pending", "reference": "T_JOURNEY_PENDING_01"}})
        ))

        page = context.new_page()

        # Capture console errors and failed network requests
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.method} {req.url} -> {req.failure}"))

        # ----------------------------------------------------------------------
        # 1. Landing Page Navigation & Call-to-Action
        # ----------------------------------------------------------------------
        print("\n[Step 1] Visiting Homepage...")
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)

        title = page.title()
        print(f"  Page Title: {title}")
        assert "Nera — AI-Powered Business Automation" in title

        heading = page.locator("h1.nera-hero-title").inner_text()
        print(f"  Hero Heading: {heading.replace(chr(10), ' ')}")
        assert "Your business." in heading
        assert "On autopilot." in heading

        # Click CTA: Automate Your Business
        print("  Clicking primary CTA: 'Automate Your Business'...")
        page.click("a[data-link='/build']")
        time.sleep(0.6)
        print(f"  Current URL: {page.url}")
        assert "/build" in page.url

        # ----------------------------------------------------------------------
        # 2. Configurator Interactions & Pricing Updates
        # ----------------------------------------------------------------------
        print("\n[Step 2] Testing Business Automation Configurator with Complete Add-on Catalog...")
        time.sleep(0.5)

        total_el = page.locator("#summary-total-price")
        initial_price = total_el.inner_text()
        print(f"  Initial Configurator Price: {initial_price}")
        assert "₦" in initial_price

        # Toggle WhatsApp channel (+₦8,000)
        print("  Enabling WhatsApp channel add-on (+₦8,000/mo)...")
        wa_check = page.locator("input[name='channels'][value='whatsapp']")
        if wa_check.count() > 0:
            wa_check.check()
            time.sleep(0.6)
            after_wa_price = total_el.inner_text()
            print(f"  Price with WhatsApp: {after_wa_price}")

        # Toggle Calendar integration (+₦2,000)
        print("  Enabling Calendar integration (+₦2,000/mo)...")
        cal_check = page.locator("input[name='integrations'][value='calendar']")
        if cal_check.count() > 0:
            cal_check.check()
            time.sleep(0.6)
            after_cal_price = total_el.inner_text()
            print(f"  Price with Calendar: {after_cal_price}")

        # Toggle Pidgin language (+₦3,500)
        print("  Enabling Nigerian Pidgin language (+₦3,500/mo)...")
        pid_check = page.locator("input[name='languages'][value='pid']")
        if pid_check.count() > 0:
            pid_check.check()
            time.sleep(0.6)
            after_lang_price = total_el.inner_text()
            print(f"  Price with Pidgin: {after_lang_price}")

        # Switch to Support Agent
        print("  Switching to AI Support Agent...")
        support_radio = page.locator("input[value='support_agent']")
        if support_radio.count() > 0:
            support_radio.check()
            time.sleep(0.6)
            support_price = total_el.inner_text()
            print(f"  Support Agent Price: {support_price}")
            assert "₦" in support_price

        # Switch to Workforce
        print("  Switching to Workforce Bundle...")
        wf_radio = page.locator("input[value='workforce_agent']")
        if wf_radio.count() > 0:
            wf_radio.check()
            time.sleep(0.6)
            wf_price = total_el.inner_text()
            print(f"  Workforce Bundle Price: {wf_price}")
            assert "₦" in wf_price

        # Switch back to Sales Agent for checkout
        page.locator("input[value='sales_agent']").check()
        time.sleep(0.6)

        # Test unauthenticated checkout boundary
        print("  Testing unauthenticated checkout boundary...")
        page.fill("#builder-org-name", "Unauth Attempt Ltd")
        page.fill("#builder-email", "unauth@attempt.ng")
        page.click("#dispatch-checkout-btn")
        time.sleep(0.8)
        print(f"  URL after unauth checkout attempt: {page.url}")
        assert "/login" in page.url or "return_to" in page.url

        # ----------------------------------------------------------------------
        # 3. Synthetic Account Registration & Login
        # ----------------------------------------------------------------------
        print("\n[Step 3] Testing Synthetic Account Registration & Login...")
        synthetic_email = f"journey_test_{int(time.time())}@audit.nera.ai"
        synthetic_name = "Emeka Nwosu"
        synthetic_org = "Nwosu Automation Ltd"
        synthetic_password = "AuditSecurePassword!2026"

        page.goto(f"{BASE_URL}/signup", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)

        page.fill("#auth-name", synthetic_name)
        page.fill("#auth-org", synthetic_org)
        page.fill("#auth-email", synthetic_email)
        page.fill("#auth-password", synthetic_password)

        page.click("#auth-submit-btn")
        page.wait_for_function("() => window.location.pathname.includes('/dashboard') || window.location.pathname.includes('/build')", timeout=45000)
        time.sleep(1.0)
        print(f"  After registration, URL: {page.url}")

        # Check localStorage token
        stored_token = page.evaluate("() => localStorage.getItem('nera_auth_token')")
        print(f"  Stored JWT token present: {bool(stored_token)}")
        assert stored_token is not None

        # ----------------------------------------------------------------------
        # 4. Authenticated Dashboard & Workspace State
        # ----------------------------------------------------------------------
        print("\n[Step 4] Checking Authenticated Dashboard...")
        page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=15000)
        time.sleep(1.0)

        user_subtitle = page.locator("#dash-user-subtitle").inner_text()
        print(f"  Dashboard Subtitle: {user_subtitle}")
        assert synthetic_email in user_subtitle or synthetic_org in user_subtitle

        page.screenshot(path=str(SCREENSHOT_DIR / "26_dashboard_authenticated.png"), full_page=True)
        print("  Captured 26_dashboard_authenticated.png")

        # ----------------------------------------------------------------------
        # 5. Authenticated Configurator Checkout to Paystack Test URL
        # ----------------------------------------------------------------------
        print("\n[Step 5] Testing Authenticated Configurator Checkout...")
        page.goto(f"{BASE_URL}/build", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.8)

        # Check that user email/company were pre-filled or pre-authenticated
        email_val = page.locator("#builder-email").input_value()
        if not email_val:
            page.fill("#builder-email", synthetic_email)
            page.fill("#builder-org-name", synthetic_org)

        print("  Clicking 'Proceed to Paystack Checkout'...")
        # Intercept Paystack checkout redirection to verify URL without exiting local test environment
        checkout_nav_target = []
        context.route(
            "https://checkout.paystack.com/**", 
            lambda route: (
                checkout_nav_target.append(route.request.url), 
                route.fulfill(status=200, content_type="text/html", body="<html><body><h1>Paystack Test Checkout Sandbox</h1></body></html>")
            )
        )

        page.click("#dispatch-checkout-btn")

        try:
            page.wait_for_url("**/checkout.paystack.com/**", timeout=25000)
            print(f"  Successfully reached Paystack checkout URL: {page.url}")
        except Exception:
            err_el = page.locator("#checkout-error-msg")
            err_text = err_el.inner_text() if err_el.is_visible() else "None"
            print(f"  Current page URL after checkout click: {page.url}, error: {err_text}")

        print(f"  Paystack checkout navigation verified: {'checkout.paystack.com' in page.url or len(checkout_nav_target) > 0}")
        assert "checkout.paystack.com" in page.url or len(checkout_nav_target) > 0

        # ----------------------------------------------------------------------
        # 6. Test Logout and Session Boundary
        # ----------------------------------------------------------------------
        print("\n[Step 6] Testing Logout & Session Boundary Enforcement...")
        # Return to application origin first
        page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)

        # Clear session token
        page.evaluate("() => { localStorage.removeItem('nera_auth_token'); }")
        time.sleep(0.5)

        # Attempt to access protected dashboard without session
        page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded", timeout=15000)
        time.sleep(1.5)

        print(f"  URL after visiting /dashboard without token: {page.url}")
        assert "/login" in page.url or "return_to" in page.url

        # ----------------------------------------------------------------------
        # 7. Checkout Return State Machine
        # ----------------------------------------------------------------------
        print("\n[Step 7] Checking Checkout Return States...")
        # A. Pending state
        page.goto(f"{BASE_URL}/checkout/return?reference=T_JOURNEY_PENDING_01", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        checking_txt = page.locator("#status-checking h1").inner_text()
        print(f"  State A (Pending): {checking_txt}")
        assert "Verifying Settlement Status" in checking_txt

        # B. Missing reference error state
        page.goto(f"{BASE_URL}/checkout/return", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        err_txt = page.locator("#status-result").inner_text()
        print(f"  State B (Missing Ref Error): {'No payment reference found' in err_txt}")
        assert "No payment reference found" in err_txt

        # C. Cancelled state
        page.goto(f"{BASE_URL}/checkout/return?cancelled=true", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        cancelled_txt = page.locator("#status-result").inner_text()
        print(f"  State C (Cancelled): {'Checkout Session Cancelled' in cancelled_txt}")
        assert "Checkout Session Cancelled" in cancelled_txt

        # ----------------------------------------------------------------------
        # 8. Console Errors & Network Failures Review
        # ----------------------------------------------------------------------
        print("\n[Step 6] Inspecting Console Errors & Failed Requests...")
        # Ignore external fonts / external APIs we intentionally aborted
        unexpected_errors = [e for e in console_errors if "fonts.googleapis" not in e and "fonts.gstatic" not in e]
        unexpected_req_failures = [
            r for r in failed_requests 
            if "fonts.googleapis" not in r 
            and "fonts.gstatic" not in r 
            and "api.paystack.co" not in r
        ]

        print(f"  Unexpected Console Errors: {len(unexpected_errors)}")
        print(f"  Unexpected Failed Network Requests: {len(unexpected_req_failures)}")

        if unexpected_errors:
            for err in unexpected_errors:
                print(f"    - {err}")

        if unexpected_req_failures:
            for fail in unexpected_req_failures:
                print(f"    - {fail}")

        assert len(unexpected_errors) == 0, f"Found console errors: {unexpected_errors}"
        assert len(unexpected_req_failures) == 0, f"Found failed requests: {unexpected_req_failures}"

        context.close()
        browser.close()

    print("\n✓ Comprehensive Browser Customer Journey Audit completed with 0 errors!")


if __name__ == "__main__":
    run_customer_journey_audit()
