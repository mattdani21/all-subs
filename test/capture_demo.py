"""Capture a demo as a frame sequence (Playwright video was unreliable here)."""
import asyncio
import os
from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
OUT = "/tmp/allsubs-frames"


async def grab(page, n, label):
    path = os.path.join(OUT, "f%03d.jpg" % n[0])
    await page.screenshot(path=path, type="jpeg", quality=82)
    n[0] += 1


async def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        os.remove(os.path.join(OUT, f))
    counter = [1]
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/allsubs-demo2",
            executable_path=EXEC, headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 1280, "height": 720},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT,
                  "--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        page = await ctx.new_page()
        await page.goto("https://www.bilibili.tv/en/video/2049319378",
                        wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)
        await page.evaluate("""() => {
            [...document.querySelectorAll('button')]
              .find(b => /got it/i.test(b.textContent))?.click();
        }""")
        await page.wait_for_timeout(600)
        for _ in range(3):
            await grab(page, counter, "page")
            await page.wait_for_timeout(300)

        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.launcher').click()")
        for _ in range(4):
            await page.wait_for_timeout(350)
            await grab(page, counter, "panel")

        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.go').click()")
        for _ in range(10):
            await page.wait_for_timeout(700)
            await grab(page, counter, "job")

        await page.evaluate("""() => {
            const r = document.querySelector('[data-allsubs-ui]').shadowRoot;
            r.querySelector('.x')?.click();
            const v = document.querySelector('video');
            v.muted = true;
            v.currentTime = 606;
        }""")
        await page.wait_for_timeout(1200)
        await page.evaluate("document.querySelector('video').play()")
        for _ in range(22):
            await page.wait_for_timeout(320)
            await grab(page, counter, "play")
        await ctx.close()
    print("frames:", counter[0] - 1)


asyncio.run(main())
