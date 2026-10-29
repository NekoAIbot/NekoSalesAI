"""
NERA 2.0 Full Visual Audit & Responsive Verification Suite.
Captures all required pages, checkout states, and tests responsive layouts across:
- 360 × 800
- 390 × 844
- 430 × 932
- 768 × 1024
- 1280 × 800
- 1440 × 900
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "/root/.gemini/antigravity-cli/brain/ea1c17dd-c7be-4245-871e-e7da1d3a6583/audit_screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000/v2"

VIEWPORTS = [
    {"name": "360x800", "width": 360, "height": 800, "is_mobile": True},
    {"name": "390x844", "width": 390, "height": 844, "is_mobile": True},
    {"name": "430x932", "width": 430, "height": 932, "is_mobile": True},
    {"name": "768x1024", "width": 768, "height": 1024, "is_mobile": False},
    {"name": "1280x800", "width": 1280, "height": 800, "is_mobile": False},
    {"name": "1440x900", "width": 1440, "height": 900, "is_mobile": False},
]

PAGES = [
    ("01_home", ""),
    ("02_products", "/products"),
    ("03_workforce", "/workforce"),
    ("04_pricing", "/pricing"),
    ("05_build", "/build"),
    ("08_demo", "/demo"),
    ("11_trust", "/trust"),
    ("12_login", "/login"),
    ("13_signup", "/signup"),
    ("14_dashboard", "/dashboard"),
]

def main():
    print("Starting Comprehensive Visual & Responsive Audit...")
    overflow_issues = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-ipv6', '--no-sandbox'])

        def configure_context(ctx):
            ctx.route("https://fonts.googleapis.com/**", lambda route: route.abort())
            ctx.route("https://fonts.gstatic.com/**", lambda route: route.abort())
            ctx.route("https://api.paystack.co/**", lambda route: route.abort())

        # 1. Capture primary desktop pages (1280x800)
        print("\n--- 1. Capturing Desktop Suite (1280x800) ---")
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        configure_context(context)
        page = context.new_page()

        for slug, path in PAGES:
            target = f"{BASE_URL}{path}"
            page.goto(target, wait_until="domcontentloaded", timeout=15000)
            time.sleep(0.5)
            fname = f"{slug}_desktop.png"
            page.screenshot(path=f"{OUTPUT_DIR}/{fname}")
            print(f"Captured: {fname}")

        # Configurator switches
        page.goto(f"{BASE_URL}/build", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.8)
        support_radio = page.locator('input[value="support_agent"]')
        if support_radio.count() > 0:
            support_radio.check()
            time.sleep(0.5)
            page.screenshot(path=f"{OUTPUT_DIR}/06_build_switched_support_desktop.png")
            print("Captured: 06_build_switched_support_desktop.png")

        wf_radio = page.locator('input[value="workforce_agent"]')
        if wf_radio.count() > 0:
            wf_radio.check()
            time.sleep(0.5)
            page.screenshot(path=f"{OUTPUT_DIR}/07_build_switched_workforce_desktop.png")
            print("Captured: 07_build_switched_workforce_desktop.png")

        # Demo tabs
        page.goto(f"{BASE_URL}/demo", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        page.click("#tab-btn-support")
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/09_demo_support_desktop.png")
        print("Captured: 09_demo_support_desktop.png")

        page.click("#tab-btn-workforce")
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/10_demo_workforce_desktop.png")
        print("Captured: 10_demo_workforce_desktop.png")

        # Checkout States:
        # State A: Pending / Checking
        print("\n--- 2. Capturing Checkout States ---")
        page.goto(f"{BASE_URL}/checkout/return?reference=T_AUDIT_PENDING_001", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/15_checkout_return_checking_desktop.png")
        print("Captured: 15_checkout_return_checking_desktop.png (Pending state)")

        # State B: Error state (missing reference)
        page.goto(f"{BASE_URL}/checkout/return", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/16_checkout_return_error_desktop.png")
        print("Captured: 16_checkout_return_error_desktop.png (Error state)")

        # State C: Cancelled state
        page.goto(f"{BASE_URL}/checkout/return?cancelled=true", wait_until="domcontentloaded", timeout=15000)
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/24_checkout_cancelled_desktop.png")
        print("Captured: 24_checkout_cancelled_desktop.png (Cancelled state)")

        # State D: Success state simulation
        page.goto(f"{BASE_URL}/checkout/return?reference=T_AUDIT_SUCCESS_001", wait_until="domcontentloaded", timeout=15000)
        page.evaluate("""() => {
            const v = window.__activeView || {};
            if (typeof v.showSuccess === 'function') {
                v.showSuccess({ status: 'success', reference: 'T_AUDIT_SUCCESS_001' });
            }
        }""")
        time.sleep(0.5)
        page.screenshot(path=f"{OUTPUT_DIR}/25_checkout_success_desktop.png")
        print("Captured: 25_checkout_success_desktop.png (Success state)")

        context.close()

        # 3. Responsive Viewport Audits across all 6 target resolutions
        print("\n--- 3. Testing Responsive Layouts across 6 Viewports ---")
        for vp in VIEWPORTS:
            ctx = browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                is_mobile=vp["is_mobile"]
            )
            configure_context(ctx)
            v_page = ctx.new_page()

            # Test Homepage on this viewport
            v_page.goto(f"{BASE_URL}", wait_until="domcontentloaded", timeout=15000)
            time.sleep(0.5)

            # Check horizontal overflow
            scroll_w = v_page.evaluate("() => document.documentElement.scrollWidth")
            inner_w = vp["width"]
            has_overflow = scroll_w > inner_w

            print(f"Viewport {vp['name']} ({vp['width']}x{vp['height']}): scrollWidth={scroll_w}, innerWidth={inner_w} -> Overflow: {has_overflow}")
            if has_overflow:
                overflow_issues.append(f"{vp['name']} horizontal overflow: {scroll_w} > {inner_w}")

            # Capture screenshot
            v_page.screenshot(path=f"{OUTPUT_DIR}/vp_{vp['name']}_home.png")

            # Also capture mobile standard 390x844 files for audit set
            if vp["name"] == "390x844":
                mob_views = [
                    ("17_home_mobile.png", f"{BASE_URL}"),
                    ("18_products_mobile.png", f"{BASE_URL}/products"),
                    ("19_workforce_mobile.png", f"{BASE_URL}/workforce"),
                    ("20_pricing_mobile.png", f"{BASE_URL}/pricing"),
                    ("21_build_mobile.png", f"{BASE_URL}/build"),
                    ("22_demo_mobile.png", f"{BASE_URL}/demo"),
                    ("23_trust_mobile.png", f"{BASE_URL}/trust"),
                ]
                for mob_fname, mob_url in mob_views:
                    v_page.goto(mob_url, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(0.5)
                    v_page.screenshot(path=f"{OUTPUT_DIR}/{mob_fname}")

            ctx.close()

        browser.close()

    print("\n--- Summary of Responsive Layout Inspection ---")
    if overflow_issues:
        print(f"WARNING: Found {len(overflow_issues)} overflow issues:")
        for issue in overflow_issues:
            print(f" - {issue}")
    else:
        print("✓ ZERO horizontal overflow across all 6 viewports (360x800, 390x844, 430x932, 768x1024, 1280x800, 1440x900).")

if __name__ == "__main__":
    main()
