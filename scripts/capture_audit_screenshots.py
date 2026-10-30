"""
Automated Playwright Audit Screenshot Suite.
Captures comprehensive desktop and mobile screenshots directly through the verified public ngrok URL:
https://splendid-grating-chaps.ngrok-free.dev/v2/
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "/root/.gemini/antigravity-cli/brain/1476abd3-4234-4d78-b43c-94b33715cba3/audit_screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "https://splendid-grating-chaps.ngrok-free.dev/v2"

def main():
    print("Launching Playwright for Audit Screenshots via ngrok...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-ipv6'])

        # -------------------------------------------------------------
        # 1. Desktop Viewport (1280x800)
        # -------------------------------------------------------------
        print("\n=== Capturing Desktop Viewport (1280x800) ===")
        desk_context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"ngrok-skip-browser-warning": "1"}
        )
        page = desk_context.new_page()

        # Homepage
        print("1. Capturing Homepage...")
        page.goto(f"{BASE_URL}", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/01_home_desktop.png")

        # Products View (Sales & Support)
        print("2. Capturing Products View...")
        page.goto(f"{BASE_URL}/products", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/02_products_sales_desktop.png")

        # Workforce View
        print("3. Capturing Workforce View...")
        page.goto(f"{BASE_URL}/workforce", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/03_workforce_desktop.png")

        # Pricing View
        print("4. Capturing Pricing View...")
        page.goto(f"{BASE_URL}/pricing", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/04_pricing_desktop.png")

        # Configurator: Initial (Sales Agent)
        print("5. Capturing Configurator (Initial Sales Agent)...")
        page.goto(f"{BASE_URL}/build", wait_until="networkidle", timeout=20000)
        time.sleep(2)
        page.screenshot(path=f"{OUTPUT_DIR}/05_build_initial_sales_desktop.png")

        # Configurator: Switched to Support Agent
        print("6. Capturing Configurator (Switched to Support Agent)...")
        support_radio = page.query_selector('input[value="support_agent"]')
        if support_radio:
            support_radio.click()
            time.sleep(2)
        page.screenshot(path=f"{OUTPUT_DIR}/06_build_switched_support_desktop.png")

        # Configurator: Switched to Workforce
        print("7. Capturing Configurator (Switched to Workforce)...")
        wf_radio = page.query_selector('input[value="workforce_agent"]')
        if wf_radio:
            wf_radio.click()
            time.sleep(2)
        page.screenshot(path=f"{OUTPUT_DIR}/07_build_switched_workforce_desktop.png")

        # Demo Studio: Sales Mode
        print("8. Capturing Demo Studio (Sales Agent Tab)...")
        page.goto(f"{BASE_URL}/demo", wait_until="networkidle", timeout=20000)
        time.sleep(2)
        page.screenshot(path=f"{OUTPUT_DIR}/08_demo_sales_desktop.png")

        # Demo Studio: Support Mode
        print("9. Capturing Demo Studio (Support Agent Tab)...")
        tab_support = page.query_selector('#tab-btn-support')
        if tab_support:
            tab_support.click()
            time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/09_demo_support_desktop.png")

        # Demo Studio: Workforce Mode
        print("10. Capturing Demo Studio (Workforce Tab)...")
        tab_wf = page.query_selector('#tab-btn-workforce')
        if tab_wf:
            tab_wf.click()
            time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/10_demo_workforce_desktop.png")

        # Trust View
        print("11. Capturing Trust & Safety...")
        page.goto(f"{BASE_URL}/trust", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/11_trust_desktop.png")

        # Auth Login
        print("12. Capturing Login...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/12_auth_login_desktop.png")

        # Auth Signup
        print("13. Capturing Signup...")
        page.goto(f"{BASE_URL}/signup", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/13_auth_signup_desktop.png")

        # Dashboard
        print("14. Capturing Dashboard...")
        page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/14_dashboard_desktop.png")

        # Checkout Return (Checking state)
        print("15. Capturing Checkout Return State...")
        page.goto(f"{BASE_URL}/checkout/return?reference=ORD-AUDIT-TEST-99", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/15_checkout_return_checking_desktop.png")

        # Checkout Return (Error/No Ref state)
        print("16. Capturing Checkout Return Error State...")
        page.goto(f"{BASE_URL}/checkout/return", wait_until="networkidle", timeout=20000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/16_checkout_return_error_desktop.png")

        desk_context.close()

        # -------------------------------------------------------------
        # 2. Mobile Viewport (390x844 - iPhone 14 / Mobile standard)
        # -------------------------------------------------------------
        print("\n=== Capturing Mobile Viewport (390x844) ===")
        mob_context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            extra_http_headers={"ngrok-skip-browser-warning": "1"}
        )
        mob_page = mob_context.new_page()

        mobile_pages = [
            ("17_home_mobile.png", ""),
            ("18_products_mobile.png", "/products"),
            ("19_workforce_mobile.png", "/workforce"),
            ("20_pricing_mobile.png", "/pricing"),
            ("21_build_mobile.png", "/build"),
            ("22_demo_mobile.png", "/demo"),
            ("23_trust_mobile.png", "/trust"),
        ]

        for fname, route in mobile_pages:
            print(f"Capturing Mobile: {route} -> {fname}...")
            mob_page.goto(f"{BASE_URL}{route}", wait_until="networkidle", timeout=20000)
            time.sleep(1)
            mob_page.screenshot(path=f"{OUTPUT_DIR}/{fname}")

        mob_context.close()
        browser.close()
        print("\n✓ All 23 audit screenshots captured successfully via ngrok!")

if __name__ == "__main__":
    main()
