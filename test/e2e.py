"""End-to-end: real bilibili page, extension panel, captions on the player."""
import asyncio
import os

from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
OUT = os.path.expanduser("~/AllSubs/test")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
URL = "https://www.bilibili.tv/en/video/2049319378"


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/allsubs-e2e-profile",
            executable_path=EXEC,
            headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 1360, "height": 860},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT,
                  "--autoplay-policy=no-user-gesture-required", "--mute-audio"],
        )
        page = await ctx.new_page()
        page.on("pageerror", lambda e: print("pageerror:", str(e)[:200]))
        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(9000)

        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.launcher').click()")
        await page.wait_for_timeout(1200)
        print("panel:", await page.evaluate("""() => {
            const r = document.querySelector('[data-allsubs-ui]').shadowRoot;
            return {open: !r.querySelector('.panel').hidden,
                    status: r.querySelector('.status').textContent,
                    title: r.querySelector('.title').textContent,
                    go: r.querySelector('.go').textContent};
        }"""))
        await page.screenshot(path=os.path.join(OUT, "shot-panel.png"))

        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.go').click()")
        await page.wait_for_timeout(5000)
        print("after go:", await page.evaluate("""() => {
            const r = document.querySelector('[data-allsubs-ui]').shadowRoot;
            return {status: r.querySelector('.status').textContent,
                    meta: r.querySelector('.meta').textContent};
        }"""))

        # jump the player into the captioned region and let the overlay render
        info = await page.evaluate("""() => new Promise((resolve) => {
            const v = document.querySelector('video');
            if (!v) return resolve({error: 'no video'});
            v.muted = true;
            v.currentTime = 3346.8;
            v.addEventListener('seeked', () => {
                v.pause();
                setTimeout(() => resolve({t: v.currentTime, dur: v.duration}), 2500);
            }, { once: true });
            setTimeout(() => resolve({t: v.currentTime, dur: v.duration}), 8000);
        })""")
        print("player:", info)
        await page.wait_for_timeout(1500)
        print("overlay:", await page.evaluate("""() => {
            const o = document.querySelector('[data-allsubs-overlay]');
            if (!o) return {present: false};
            const r = o.shadowRoot;
            return {present: true, dst: r.querySelector('.dst').textContent,
                    src: r.querySelector('.src').textContent,
                    badge: r.querySelector('.badge').textContent};
        }"""))
        await page.screenshot(path=os.path.join(OUT, "shot-live.png"))
        await ctx.close()


asyncio.run(main())
