"""Capture a real console chat session as an animated GIF (README demo).

Requires a model to be loaded on the server first (e.g. via the API or
console Models page). Uses Playwright + system Chrome to drive the real
UI and Pillow to compose frames.

Usage: python scripts/capture_console_gif.py [--base http://127.0.0.1:8765]
"""
import argparse
import os
import sys

from playwright.sync_api import sync_playwright

CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
OUT = os.path.join("docs", "screenshots", "demo-chat.gif")
PROMPT = (
    "Explain, in three or four sentences, how memory-mapped GGUF files "
    "let a 100 GB model run on a machine with only 64 GB of RAM."
)
FRAME_MS = 500
GIF_WIDTH = 720


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    args = ap.parse_args()

    from PIL import Image

    frames = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--disable-gpu", "--hide-scrollbars"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{args.base}/console/?locale=en#/chat", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("textarea.chat__input", timeout=30000)
        page.wait_for_timeout(1500)

        def snap():
            frames.append(page.screenshot())

        # frame 0: empty composer, model chip loaded
        snap()
        # type the prompt
        page.fill("textarea.chat__input", PROMPT)
        page.wait_for_timeout(400)
        snap()
        # send — start capturing immediately so the streaming is visible
        page.click(".chat__composer-meta button.btn--primary")
        snap()
        # capture during streaming until the Stop button disappears
        last_len = -1
        stable = 0
        while True:
            page.wait_for_timeout(FRAME_MS)
            snap()
            stop = page.query_selector("button.btn--danger")
            msgs = page.eval_on_selector_all(
                ".chat__bubble .content, .chat__bubble p",
                "els => els.map(e => e.innerText).join(' ').length",
            ) if page.query_selector(".chat__bubble") else 0
            if not stop:
                if msgs == last_len:
                    stable += 1
                else:
                    stable = 0
                if stable >= 2:  # answer finished + settled
                    break
            last_len = msgs
            if len(frames) > 90:  # hard cap
                break
        page.wait_for_timeout(800)
        snap()
        # bonus: live stats page with real telemetry
        page.goto(f"{args.base}/console/?locale=en#/stats", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("text=Live Stats", timeout=20000)
        page.wait_for_timeout(2500)
        snap()
        snap()
        browser.close()

    # compose GIF (imageio writer — keeps every frame)
    import imageio.v2 as iio

    imgs = []
    for f in frames:
        im = Image.open(__import__("io").BytesIO(f)).convert("RGB")
        h = int(im.height * GIF_WIDTH / im.width)
        im = im.resize((GIF_WIDTH, h), Image.LANCZOS)
        imgs.append(im)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    iio.mimsave(
        OUT,
        imgs,
        duration=FRAME_MS / 1000.0,
        loop=0,
    )
    size_mb = os.path.getsize(OUT) / 1e6
    print(f"wrote {OUT}: {len(imgs)} frames, {GIF_WIDTH}px, {size_mb:.2f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
