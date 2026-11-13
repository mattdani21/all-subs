"""Onboarding check: options page renders, panel shows Settings, health is read."""
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
            user_data_dir="/tmp/allsubs-onboarding",
            executable_path=EXEC, headless=True,
            ignore_default_args=["--disable-extensions"],
            viewport={"width": 900, "height": 1100},
            args=["--disable-extensions-except=" + EXT, "--load-extension=" + EXT],
        )
        page = await ctx.new_page()
        await page.goto("http://127.0.0.1:8899/test/blank.html")
        await page.wait_for_timeout(2500)
        sw = ctx.service_workers[0].url if ctx.service_workers else ""
        ext_id = sw.split("/")[2] if sw else ""
        print("id:", ext_id)

        opts = await ctx.new_page()
        await opts.goto("chrome-extension://%s/options.html" % ext_id)
        await opts.wait_for_timeout(2500)
        dots = await opts.evaluate("""() => {
            const out = {};
            document.querySelectorAll('.dot').forEach(d => {
                out[d.dataset.k] = d.className.replace('dot', '').trim();
            });
            return {dots: out, status: document.getElementById('status').textContent};
        }""")
        print("options:", dots)
        await opts.screenshot(path=os.path.join(OUT, "shot-options.png"), full_page=True)

        await page.evaluate(
            "document.querySelector('[data-allsubs-ui]').shadowRoot"
            ".querySelector('.launcher').click()")
        await page.wait_for_timeout(1800)
        panel = await page.evaluate("""() => {
            const r = document.querySelector('[data-allsubs-ui]').shadowRoot;
            return {open: !r.querySelector('.panel').hidden,
                    status: r.querySelector('.status').textContent,
                    settings: !!r.querySelector('[data-el="settings"]'),
                    localDisabled: r.querySelector('[data-el="local"]').disabled};
        }""")
        print("panel:", panel)
        await page.screenshot(path=os.path.join(OUT, "shot-panel-onboarding.png"))
        await ctx.close()


asyncio.run(main())
