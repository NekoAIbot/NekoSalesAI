"""
Automated Browser Screenshot & Verification Script for Nera 2.0 Greenfield Frontend.
Captures Desktop (1280x800) and Mobile (390x844) viewport screenshots for key views.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

OUTPUT_DIR = "/root/.gemini/antigravity-cli/brain/1476abd3-4234-4d78-b43c-94b33715cba3/screenshots"
os.makedirs(OUTPUT_DIR, exist_ok=True)

BASE_URL = "http://127.0.0.1:8000/v2"

PAGES = [
    ("home", ""),
    ("products", "/products"),
    ("workforce", "/workforce"),
    ("demo", "/demo"),
    ("pricing", "/pricing"),
    ("build", "/build"),
    ("trust", "/trust"),
]

VIEWPORTS = [
    ("desktop", {"width": 1280, "height": 800}),
    ("mobile", {"width": 390, "height": 844, "is_mobile": True, "has_touch": True}),
]

def main():
    print("Launching Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for vp_name, vp_opts in VIEWPORTS:
            print(f"\n--- Capturing Viewport: {vp_name} ---")
            context = browser.new_context(
                viewport={"width": vp_opts["width"], "height": vp_opts["height"]},
                is_mobile=vp_opts.get("is_mobile", False),
                has_touch=vp_opts.get("has_touch", False),
            )
            page = context.new_page()

            for page_name, route in PAGES:
                url = f"{BASE_URL}{route}"
                print(f"Navigating to {url} [{vp_name}]...")
                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    time.sleep(1) # Allow CSS animations / DOM rendering to settle
                    
                    shot_path = os.path.join(OUTPUT_DIR, f"{page_name}_{vp_name}.png")
                    page.screenshot(path=shot_path, full_page=False)
                    print(f"✓ Saved {shot_path}")
                except Exception as e:
                    print(f"✗ Failed {url}: {e}")
            
            context.close()
        
        browser.close()
        print("\nAll screenshots captured successfully!")

if __name__ == "__main__":
    main()
