"""Capture console screenshots for README (Playwright + system Chrome).

Usage: python scripts/capture_console_shots.py [--out docs/screenshots] [--base http://127.0.0.1:8765]
"""
import argparse
import os
import sys

from playwright.sync_api import sync_playwright

CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
ROUTES = [
    ("overview", "01-overview", "text=Overview"),
    ("models", "02-models", "text=LOADED MODELS"),
    ("stats", "03-stats", "text=Live Stats"),
    ("settings", "04-settings", "text=Settings"),
    ("hub", "05-hub", "text=Hub"),
    ("chat", "06-chat", "text=Chat"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/screenshots")
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            headless=True,
            args=["--disable-gpu", "--hide-scrollbars"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for route, name, ready_selector in ROUTES:
            url = f"{args.base}/console/?locale=en#/{route}"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector(ready_selector, timeout=20000)
            except Exception as e:
                print(f"[warn] {name}: ready selector not found: {e}")
            page.wait_for_timeout(2500)  # let telemetry fetch + charts settle
            path = os.path.join(args.out, f"{name}.png")
            page.screenshot(path=path, full_page=True)
            print(f"[ok] {name} -> {path}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
