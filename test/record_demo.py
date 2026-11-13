"""Record a short demo: real page, panel, captions appear, film plays."""
import asyncio
import os
from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
VID = "/tmp/allsubs-rec"


async def main():
    os.makedirs(VID, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/allsubs-demo-profile",
            executable_path=EXEC, headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 1280, "height": 720},
            record_video_dir=VID, record_video_size={"width": 1280, "height": 720},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT,
                  "--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        page = await ctx.new_page()
        await page.goto("https://www.bilibili.tv/en/video/2049319378",
                        wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(6000)
        # dismiss the cookie banner if present
        await page.evaluate("""() => {
            [...document.querySelectorAll('button')]
              .find(b => /got it/i.test(b.textContent))?.click();
        }""")
        await page.wait_for_timeout(1200)
        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.launcher').click()")
        await page.wait_for_timeout(1500)
        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.go').click()")
        await page.wait_for_timeout(9000)
        # close panel, jump the player to a captioned moment and let it play
        await page.evaluate("""() => {
            const r = document.querySelector('[data-allsubs-ui]').shadowRoot;
            r.querySelector('.x')?.click();
            const v = document.querySelector('video');
            v.muted = true;
            v.currentTime = 610;
        }""")
        await page.wait_for_timeout(2500)
        await page.evaluate("document.querySelector('video').play()")
        await page.wait_for_timeout(8000)
        await ctx.close()


asyncio.run(main())
