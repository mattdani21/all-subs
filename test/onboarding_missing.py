"""Missing-key state: point the options page at a stub that reports no keys."""
import asyncio
import os
from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
OUT = os.path.expanduser("~/AllSubs/test")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/allsubs-onboarding2",
            executable_path=EXEC, headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 900, "height": 1100},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT],
        )
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:8899/test/blank.html")
        await page.wait_for_timeout(2000)
        ext_id = ctx.service_workers[0].url.split("/")[2] if ctx.service_workers else ""
        opts = await ctx.new_page()
        await opts.goto("chrome-extension://%s/options.html" % ext_id)
        await opts.wait_for_timeout(1500)
        await opts.fill("#backend", "http://127.0.0.1:8898")
        await opts.click("#test")
        await opts.wait_for_timeout(1200)
        state = await opts.evaluate("""() => ({
            status: document.getElementById('status').textContent,
            kind: document.getElementById('status').className,
            ds: document.querySelector('.dot[data-k=deepseek_key]').className,
            local: document.getElementById('local').disabled
        })""")
        print("missing-key state:", state)
        await opts.screenshot(path=os.path.join(OUT, "shot-options-missing.png"), full_page=True)
        await ctx.close()


asyncio.run(main())
