"""Simple single-page screenshot."""
import asyncio
from pathlib import Path

OUT = Path("/home/user/screenshots")

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto("http://127.0.0.1:8000/build", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT / "build_simple.png"), full_page=True)
        print("OK: build_simple.png")
        await browser.close()

asyncio.run(main())
