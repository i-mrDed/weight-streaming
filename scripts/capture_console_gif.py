"""Capture a real console chat session as an animated GIF (README demo).

Requires a model to be loaded on the server first (e.g. via the API or
console Models page). Uses Playwright + system Chrome to drive the real
UI and Pillow to compose frames.

Usage: python scripts/capture_console_gif.py [--base http://127.0.0.1:8765]
"""
import argparse
import io
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
FRAMES_DIR = os.path.join("scripts", ".demo_frames")


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
            # keep individual PNGs too, so ffmpeg can encode webm/mp4 with
            # correct timing (imageio's GIF writer mangles frame delays)
            os.makedirs(FRAMES_DIR, exist_ok=True)
            with open(
                os.path.join(FRAMES_DIR, f"frame_{len(frames):03d}.png"), "wb"
            ) as f:
                f.write(frames[-1])

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

    # compose GIF with Pillow directly: optimize=False keeps every frame and
    # duration=FRAME_MS sets real timing (imageio wrote ~0 ms delays)
    imgs = []
    for f in frames:
        im = Image.open(io.BytesIO(f)).convert("RGB")
        h = int(im.height * GIF_WIDTH / im.width)
        im = im.resize((GIF_WIDTH, h), Image.LANCZOS)
        imgs.append(im)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    imgs[0].save(
        OUT,
        save_all=True,
        append_images=imgs[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=False,
    )
    size_mb = os.path.getsize(OUT) / 1e6
    print(f"wrote {OUT}: {len(imgs)} frames, {GIF_WIDTH}px, {size_mb:.2f} MB")
    print(f"frames kept in {FRAMES_DIR} for webm/mp4 encode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
