"""Screenshot harness: loads the unpacked extension in Chrome for Testing and
shoots the local player harness plus a real bilibili page."""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
OUT = os.path.expanduser("~/AllSubs/test")
PROFILE = "/tmp/allsubs-cft-profile"
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            executable_path=EXEC,
            headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-extensions-except=" + EXT,
                "--load-extension=" + EXT,
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio",
            ],
        )
        blank = await ctx.new_page()
        await blank.goto("http://127.0.0.1:8899/test/blank.html")
        await blank.wait_for_timeout(4000)
        print("workers:", [w.url for w in ctx.service_workers])
        print("blank:", await blank.evaluate(
            "({host: !!document.querySelector('[data-allsubs-ui]'), "
            "err: document.documentElement.getAttribute('data-allsubs-error'), "
            "videos: document.querySelectorAll('video').length})"))
        await blank.screenshot(path=os.path.join(OUT, "shot-extension.png"))

        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:8899/test/player.html"
                        "?job=a215b31098bb&src=/media/shadow_144.mp4&t=620.2")
        await page.wait_for_timeout(2500)
        await page.evaluate("""() => new Promise((resolve) => {
            const v = document.querySelector('video');
            v.muted = true;
            const target = 620.2;
            const done = () => { v.pause(); resolve(true); };
            if (Math.abs(v.currentTime - target) < 0.3) return done();
            v.addEventListener('seeked', done, { once: true });
            v.currentTime = target;
            setTimeout(done, 6000);
        })""")
        await page.wait_for_timeout(3500)
        await page.screenshot(path=os.path.join(OUT, "shot-overlay.png"))
        print("harness:", await page.evaluate("""() => {
            const v = document.querySelector('video');
            return {t: v ? v.currentTime : -1, paused: v ? v.paused : null,
                    host: !!document.querySelector('[data-allsubs-ui]')};
        }"""))

        real = await ctx.new_page()
        await real.goto("https://www.bilibili.tv/en/video/2049319378",
                        wait_until="domcontentloaded", timeout=90000)
        await real.wait_for_timeout(10000)
        await real.screenshot(path=os.path.join(OUT, "shot-bilibili.png"))
        print("bilibili:", await real.evaluate("""() => {
            const host = document.querySelector('[data-allsubs-ui]');
            return {host: !!host,
                    button: host ? !!host.shadowRoot.querySelector('.launcher') : false,
                    videos: document.querySelectorAll('video').length};
        }"""))
        await ctx.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("FAILED:", exc)
        sys.exit(1)
