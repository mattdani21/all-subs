import asyncio, os
from playwright.async_api import async_playwright

EXEC = os.path.expanduser("~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
                          "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXEC, headless=True)
        page = await b.new_page(viewport={"width": 1280, "height": 720})
        await page.goto("http://127.0.0.1:8899/test/player.html?job=277eff5df19e&src=/media/shadow_144.mp4&t=611.6")
        await page.wait_for_timeout(4000)
        info = await page.evaluate("""() => {
            const v = document.querySelector('video');
            const o = document.querySelector('[data-allsubs-overlay]');
            const r = o && o.shadowRoot;
            return {
                t: v && v.currentTime, paused: v && v.paused,
                overlay: !!o,
                dst: r && r.querySelector('.dst') ? r.querySelector('.dst').textContent : null,
                src: r && r.querySelector('.src') ? r.querySelector('.src').textContent : null,
                cls: r && r.querySelector('.dst') ? r.querySelector('.dst').className : null,
                rect: o ? o.getBoundingClientRect().toJSON() : null,
                vrect: v ? v.getBoundingClientRect().toJSON() : null
            };
        }""")
        print(info)
        await page.screenshot(path="/Users/matt/AllSubs/test/debug-harness.png")
        await b.close()

asyncio.run(main())
