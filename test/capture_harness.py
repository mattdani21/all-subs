"""Capture the local harness playing the library-track job (real overlay, real cues)."""
import asyncio
import os
from playwright.async_api import async_playwright

EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
OUT = "/tmp/allsubs-frames2"
URL = ("http://127.0.0.1:8899/test/player.html"
       "?job=277eff5df19e&src=/media/shadow_144.mp4&t=606")


async def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    n = 0
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXEC, headless=True)
        page = await b.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        await page.evaluate("document.querySelector('video').play()")
        for _ in range(26):
            n += 1
            await page.screenshot(path=os.path.join(OUT, "f%03d.jpg" % n),
                                  type="jpeg", quality=85)
            await page.wait_for_timeout(320)
        print("frames", n)
        await b.close()


asyncio.run(main())
