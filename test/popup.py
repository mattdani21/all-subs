"""Loads the popup page itself and screenshots it (engine status + button)."""
import asyncio, os
from playwright.async_api import async_playwright

EXT = os.path.expanduser("~/AllSubs/extension")
EXEC = os.path.expanduser(
    "~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")


async def main():
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/allsubs-popup-profile",
            executable_path=EXEC, headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 380, "height": 260},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT],
        )
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:8899/test/blank.html")
        await page.wait_for_timeout(2500)
        sw = ctx.service_workers[0].url if ctx.service_workers else ""
        ext_id = sw.split("/")[2] if sw else ""
        print("id:", ext_id)
        pop = await ctx.new_page()
        await pop.goto("chrome-extension://%s/popup.html" % ext_id)
        await pop.wait_for_timeout(2500)
        print("status:", await pop.inner_text("#status"))
        print("dot:", await pop.get_attribute("#dot", "class"))
        await pop.screenshot(path=os.path.expanduser("~/AllSubs/test/shot-popup.png"))
        await ctx.close()

asyncio.run(main())
