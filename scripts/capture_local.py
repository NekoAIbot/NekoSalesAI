"""Capture screenshots of local NekoSalesAI server."""
import asyncio
from pathlib import Path

OUT = Path("/home/user/screenshots")
OUT.mkdir(exist_ok=True)

URL = "http://127.0.0.1:8000"

PAGES = [
    ("landing", "/"),
    ("build", "/build"),
    ("products", "/products"),
    ("pricing", "/pricing"),
    ("login", "/login"),
    ("signup", "/signup"),
    ("trust", "/trust"),
]

async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        # Desktop screenshots
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        for name, path in PAGES:
            page = await context.new_page()
            try:
                await page.goto(f"{URL}{path}", wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)
                await page.screenshot(path=str(OUT / f"{name}_desktop.png"), full_page=True)
                print(f"OK: {name}_desktop.png")
            except Exception as e:
                print(f"FAIL: {name}_desktop.png - {e}")
            await page.close()
        await context.close()

        # Mobile screenshots
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        for name, path in PAGES:
            page = await context.new_page()
            try:
                await page.goto(f"{URL}{path}", wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)
                await page.screenshot(path=str(OUT / f"{name}_mobile.png"), full_page=True)
                print(f"OK: {name}_mobile.png")
            except Exception as e:
                print(f"FAIL: {name}_mobile.png - {e}")
            await page.close()
        await context.close()

        # Build page interactions
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
        )
        page = await context.new_page()
        try:
            await page.goto(f"{URL}/build", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            
            # Default view
            await page.screenshot(path=str(OUT / "build_default.png"), full_page=True)
            print("OK: build_default.png")
            
            # Wait for price to appear
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(OUT / "build_priced.png"), full_page=True)
            print("OK: build_priced.png")

            # Select workforce
            wf = await page.query_selector("[data-builder-product='workforce_agent']")
            if wf:
                await wf.click()
                await page.wait_for_timeout(1500)
                await page.screenshot(path=str(OUT / "build_workforce.png"), full_page=True)
                print("OK: build_workforce.png")

            # Select integrations
            integs = await page.query_selector_all("[data-builder-integration]")
            for i, el in enumerate(integs[:3]):
                await el.click()
                await page.wait_for_timeout(200)
            await page.wait_for_timeout(1000)
            await page.screenshot(path=str(OUT / "build_integrations.png"), full_page=True)
            print("OK: build_integrations.png")

            # Change volume
            vol = await page.query_selector("[data-vol='2500']")
            if vol:
                await vol.click()
                await page.wait_for_timeout(1000)
                await page.screenshot(path=str(OUT / "build_vol_2500.png"), full_page=True)
                print("OK: build_vol_2500.png")

        except Exception as e:
            print(f"FAIL: build interactions - {e}")
        await page.close()
        await context.close()

        await browser.close()
        print("DONE")

if __name__ == "__main__":
    asyncio.run(main())
