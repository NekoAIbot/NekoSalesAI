"""
Capture comprehensive screenshots of Nera AI-Powered Business Automation.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "/root/.gemini/antigravity-cli/brain/1476abd3-4234-4d78-b43c-94b33715cba3/audit_screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000/v2"

def main():
    print("Launching Playwright for Automation Screenshots...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-ipv6', '--no-sandbox'])

        # -------------------------------------------------------------
        # 1. Desktop Viewport (1280x800)
        # -------------------------------------------------------------
        print("\n=== Capturing Desktop Viewport (1280x800) ===")
        desk_context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = desk_context.new_page()

        # Homepage
        print("1. Capturing Homepage...")
        page.goto(f"{BASE_URL}", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/01_home_desktop.png")

        # Products View (Sales & Support Automation)
        print("2. Capturing Products View...")
        page.goto(f"{BASE_URL}/products", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/02_products_sales_desktop.png")

        # Workforce View
        print("3. Capturing Workforce View...")
        page.goto(f"{BASE_URL}/workforce", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/03_workforce_desktop.png")

        # Pricing View
        print("4. Capturing Pricing View...")
        page.goto(f"{BASE_URL}/pricing", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/04_pricing_desktop.png")

        # Configurator: Initial (Sales Engine)
        print("5. Capturing Configurator (Initial Sales Engine)...")
        page.goto(f"{BASE_URL}/build", wait_until="networkidle", timeout=15000)
        time.sleep(1.5)
        page.screenshot(path=f"{OUTPUT_DIR}/05_build_initial_sales_desktop.png")

        # Configurator: Switched to Support Engine
        print("6. Capturing Configurator (Switched Support Engine)...")
        support_radio = page.locator('input[value="support_agent"]')
        if support_radio.count() > 0:
            support_radio.check()
            time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/06_build_switched_support_desktop.png")

        # Configurator: Switched to Workforce Pipeline
        print("7. Capturing Configurator (Switched Workforce Pipeline)...")
        wf_radio = page.locator('input[value="workforce_agent"]')
        if wf_radio.count() > 0:
            wf_radio.check()
            time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/07_build_switched_workforce_desktop.png")

        # Demo: Sales Tab
        print("8. Capturing Demo Studio (Sales)...")
        page.goto(f"{BASE_URL}/demo", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/08_demo_sales_desktop.png")

        # Demo: Support Tab
        print("9. Capturing Demo Studio (Support)...")
        page.click("#tab-btn-support")
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/09_demo_support_desktop.png")

        # Demo: Workforce Tab
        print("10. Capturing Demo Studio (Workforce)...")
        page.click("#tab-btn-workforce")
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/10_demo_workforce_desktop.png")

        # Trust View
        print("11. Capturing Trust View...")
        page.goto(f"{BASE_URL}/trust", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/11_trust_desktop.png")

        # Auth Login
        print("12. Capturing Auth Login...")
        page.goto(f"{BASE_URL}/login", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/12_auth_login_desktop.png")

        # Auth Signup
        print("13. Capturing Auth Signup...")
        page.goto(f"{BASE_URL}/signup", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/13_auth_signup_desktop.png")

        # Dashboard View
        print("14. Capturing Dashboard View...")
        page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/14_dashboard_desktop.png")

        # Checkout Return: Checking State
        print("15. Capturing Checkout Return (Checking State)...")
        page.goto(f"{BASE_URL}/checkout/return?reference=T_AUDIT_VERIFY_4029", wait_until="networkidle", timeout=15000)
        time.sleep(1)
        page.screenshot(path=f"{OUTPUT_DIR}/15_checkout_return_checking_desktop.png")

        desk_context.close()

        # -------------------------------------------------------------
        # 2. Mobile Viewport (390x844 - iPhone / Modern Android)
        # -------------------------------------------------------------
        print("\n=== Capturing Mobile Viewport (390x844) ===")
        mob_context = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True
        )
        mob_page = mob_context.new_page()

        mob_views = [
            ("17_home_mobile.png", f"{BASE_URL}"),
            ("18_products_mobile.png", f"{BASE_URL}/products"),
            ("19_workforce_mobile.png", f"{BASE_URL}/workforce"),
            ("20_pricing_mobile.png", f"{BASE_URL}/pricing"),
            ("21_build_mobile.png", f"{BASE_URL}/build"),
            ("22_demo_mobile.png", f"{BASE_URL}/demo"),
            ("23_trust_mobile.png", f"{BASE_URL}/trust"),
        ]

        for fname, url in mob_views:
            print(f"Mobile: Capturing {fname}...")
            mob_page.goto(url, wait_until="networkidle", timeout=15000)
            time.sleep(1)
            mob_page.screenshot(path=f"{OUTPUT_DIR}/{fname}")

        mob_context.close()
        browser.close()
        print("\n✓ All screenshots captured successfully!")

if __name__ == "__main__":
    main()
