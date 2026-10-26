"""Assemble docs/images/app-tour.gif from the screenshots in docs/images/.

Run after `npm run screenshots` (from frontend/). Needs Pillow:
    pip install pillow
    python scripts/make_app_tour.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGES = Path(__file__).resolve().parent.parent / "docs" / "images"
FRAMES = [
    ("in-laptop-chat.png", "Paste a job link: get a match score, matched and missing skills", 3200),
    ("final-laptop.png", "One click tailors your CV: edit the draft, export PDF, DOCX or HTML", 3200),
    ("combo-chat.png", "Unreadable link? The assistant says why and asks for the text", 3200),
    ("combo-dark.png", "Dark mode", 2600),
    ("combo-mobile.png", "Mobile layout", 2600),
]
WIDTH, HEIGHT, CAPTION = 1200, 780, 44


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    font = _font(20)
    frames, durations = [], []
    for filename, caption, ms in FRAMES:
        shot = Image.open(IMAGES / filename).convert("RGB")
        scale = min(WIDTH / shot.width, (HEIGHT - CAPTION) / shot.height)
        shot = shot.resize((int(shot.width * scale), int(shot.height * scale)), Image.LANCZOS)
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (250, 248, 244))
        canvas.paste(shot, ((WIDTH - shot.width) // 2, 0))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, HEIGHT - CAPTION, WIDTH, HEIGHT], fill=(32, 30, 28))
        text_width = draw.textlength(caption, font=font)
        draw.text(((WIDTH - text_width) / 2, HEIGHT - CAPTION + 10), caption, font=font, fill=(255, 255, 255))
        frames.append(canvas.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE))
        durations.append(ms)
    frames[0].save(
        IMAGES / "app-tour.gif", save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True,
    )
    print(f"wrote {IMAGES / 'app-tour.gif'}")


if __name__ == "__main__":
    main()
