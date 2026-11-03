import asyncio, os
from playwright.async_api import async_playwright

URL = "https://excalidraw.com/#json=1ofxsj4VZtpdu1rEuOcxR,Ba6QGybROqrC7KSEQ4ZgWQ"
OUT = os.path.expanduser("~/AllSubs/docs/allsubs-pipeline.png")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXEC, headless=True)
        page = await b.new_page(viewport={"width": 1500, "height": 1600})
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(7000)
        await page.keyboard.press("Shift+1")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=OUT, full_page=False)
        print("shot", OUT)
        await b.close()

asyncio.run(main())
