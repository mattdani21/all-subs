import asyncio, os
from playwright.async_api import async_playwright

EXEC = os.path.expanduser("~/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
                          "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
OUT = os.path.expanduser("~/AllSubs/docs")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXEC, headless=True)
        page = await b.new_page(viewport={"width": 1280, "height": 720})
        await page.goto("http://127.0.0.1:8899/test/player.html"
                        "?job=277eff5df19e&src=/media/shadow_144.mp4&t=611.6")
        await page.wait_for_timeout(3500)
        await page.evaluate("""() => {
            const v = document.querySelector('video');
            v.removeAttribute('controls');
            v.pause();
            v.currentTime = 611.6;
            document.querySelector('header').style.display = 'none';
            document.querySelectorAll('.bar, p.hint').forEach(e => e.style.display = 'none');
            document.body.style.background = '#000';
            document.querySelector('.stage').style.margin = '0';
            document.querySelector('.stage').style.padding = '0';
        }""")
        await page.wait_for_timeout(900)
        rect = await page.evaluate("""() => {
            const r = document.querySelector('video').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""")
        await page.screenshot(path=os.path.join(OUT, "hero.png"), clip=rect)
        print("hero", rect)
        await b.close()

asyncio.run(main())
