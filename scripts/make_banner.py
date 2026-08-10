"""Generate the README/social-preview banner (docs/screenshots/banner.png).

Pure PIL, no external deps beyond pillow. 1280x640 (GitHub social preview
ratio ~1.91:1).
"""
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 640
OUT = os.path.join("docs", "screenshots", "banner.png")

BG_TOP = (11, 15, 25)      # #0b0f19
BG_BOT = (17, 24, 42)      # #11182a
ACCENT = [(56, 189, 248), (129, 140, 248), (217, 70, 239)]  # blue→indigo→fuchsia

FONT_TITLE = r"C:/Windows/Fonts/seguisb.ttf"
FONT_BODY = r"C:/Windows/Fonts/arialbd.ttf"
FONT_MONO = r"C:/Windows/Fonts/consolab.ttf"


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main() -> None:
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        t = y / (H - 1)
        c = lerp(BG_TOP, BG_BOT, t)
        for x in range(W):
            px[x, y] = c

    d = ImageDraw.Draw(im)

    # accent glow band near the bottom (soft horizontal gradient bars)
    for i, col in enumerate(ACCENT):
        x0 = 90 + i * 34
        x1 = x0 + 26
        for x in range(x0, min(x1, W)):
            for y in range(430, 466):
                r, g, b = px[x, y]
                px[x, y] = (min(255, r + col[0] // 3), min(255, g + col[1] // 3), min(255, b + col[2] // 3))

    # small "W" logo mark: rounded square with gradient
    for i, col in enumerate(ACCENT):
        for x in range(86, 138):
            for y in range(96, 148):
                r, g, b = px[x, y]
                px[x, y] = (min(255, r + col[0] // 4), min(255, g + col[1] // 4), min(255, b + col[2] // 4))

    title_f = ImageFont.truetype(FONT_TITLE, 56)
    body_f = ImageFont.truetype(FONT_BODY, 24)
    mono_f = ImageFont.truetype(FONT_MONO, 22)

    d.text((90, 180), "Weight Streaming", font=title_f, fill=(235, 240, 250))
    d.text((96, 262), "Run LLMs larger than your RAM — measured honestly.", font=body_f, fill=(150, 165, 195))

    chips = ["llama.cpp / GGUF", "MoE 100B–3T+", "NVMe-as-memory", "honest telemetry"]
    x = 96
    for chip in chips:
        w = d.textlength(chip, font=mono_f) + 36
        d.rounded_rectangle((x, 320, x + w, 362), radius=21, fill=(28, 37, 54), outline=(56, 70, 100))
        d.text((x + 18, 328), chip, font=mono_f, fill=(170, 195, 235))
        x += w + 16

    d.text((96, 430), "tok/s · page faults/token · disk MB/token — real numbers, or n/a. Never fabricated.",
           font=mono_f, fill=(120, 138, 175))

    im.save(OUT, "PNG")
    print(f"wrote {OUT} ({W}x{H})")


if __name__ == "__main__":
    main()
