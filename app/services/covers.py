"""Cover / thumbnail / placeholder images with Pillow (no external assets)."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .fonts import japanese_font, latin_font


def _hex(color: str, default=(55, 229, 255)) -> tuple[int, int, int]:
    c = (color or "").strip().lstrip("#")
    if len(c) == 6:
        try:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            pass
    return default


def _font(size: int, ja: bool = False) -> ImageFont.ImageFont:
    path = japanese_font() if ja else latin_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def gradient_bg(w: int, h: int, c1: str, c2: str, seed: int = 0) -> Image.Image:
    a, b = _hex(c1), _hex(c2, (138, 92, 255))
    img = Image.new("RGB", (w, h))
    px = img.load()
    rng = random.Random(seed)
    angle = rng.uniform(0.3, 1.2)
    for y in range(h):
        for x in range(0, w):
            t = (x * math.cos(angle) + y * math.sin(angle)) / (w * math.cos(angle) + h * math.sin(angle))
            t = max(0.0, min(1.0, t))
            px[x, y] = tuple(int(a[i] * (1 - t) * 0.35 + b[i] * t * 0.35) for i in range(3))
    # glow orbs
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    for _ in range(4):
        r = rng.randint(w // 6, w // 2)
        cx, cy = rng.randint(0, w), rng.randint(0, h)
        col = a if rng.random() < 0.5 else b
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(int(v * 0.5) for v in col))
    glow = glow.filter(ImageFilter.GaussianBlur(w // 8))
    return Image.blend(img, Image.eval(glow, lambda v: v), 0.5)


def triangle_mark(img: Image.Image, cx: int, cy: int, size: int, color: str) -> None:
    d = ImageDraw.Draw(img)
    c = _hex(color)
    pts = [(cx, cy - size), (cx - size * 0.87, cy + size * 0.5), (cx + size * 0.87, cy + size * 0.5)]
    d.polygon(pts, outline=c, width=max(2, size // 12))


def placeholder_character(path: Path, w: int = 1024, h: int = 1024, color: str = "#37E5FF", seed: int = 1) -> Path:
    """Abstract identity card used ONLY when no approved reference image exists.

    It is deliberately non-figurative (no face) so it cannot be mistaken for the
    character; the UI labels it 「基準画像未確定」.
    """
    img = gradient_bg(w, h, color, "#8A5CFF", seed)
    triangle_mark(img, w // 2, h // 2, w // 5, color)
    d = ImageDraw.Draw(img)
    f = _font(w // 22, ja=True)
    d.text((w // 2, int(h * 0.82)), "基準画像未確定", font=f, fill=(230, 230, 230), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    ratio = max(w / img.width, h / img.height)
    im = img.resize((int(img.width * ratio) + 1, int(img.height * ratio) + 1), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def _shadow_text(d: ImageDraw.ImageDraw, xy, text, font, fill, anchor="mm"):
    x, y = xy
    d.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0), anchor=anchor)
    d.text((x, y), text, font=font, fill=fill, anchor=anchor)


def make_cover(out: Path, w: int, h: int, title: str, artist: str, accent: str, base_image: Path | None, seed: int, subtitle: str = "") -> Path:
    if base_image and base_image.exists():
        try:
            img = _fit(Image.open(base_image).convert("RGB"), w, h)
            img = Image.blend(img, gradient_bg(w, h, accent, "#8A5CFF", seed), 0.18)
        except OSError:
            img = gradient_bg(w, h, accent, "#8A5CFF", seed)
    else:
        img = gradient_bg(w, h, accent, "#8A5CFF", seed)
        triangle_mark(img, w // 2, int(h * 0.42), min(w, h) // 6, accent)
    # bottom darkening for legibility
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(h // 3):
        od.line([(0, h - i), (w, h - i)], fill=(0, 0, 0, int(170 * (1 - i / (h / 3)))))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    big = _font(int(min(w, h) * 0.085))
    small = _font(int(min(w, h) * 0.045))
    ja = _font(int(min(w, h) * 0.04), ja=True)
    _shadow_text(d, (w // 2, int(h * 0.80)), title[:32], big, (255, 255, 255))
    _shadow_text(d, (w // 2, int(h * 0.88)), artist, small, _hex(accent))
    if subtitle:
        _shadow_text(d, (w // 2, int(h * 0.94)), subtitle[:40], ja, (220, 220, 220))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def make_all_covers(out_dir: Path, title: str, artist: str, accent: str, base_image: Path | None, seed: int, subtitle: str = "") -> dict[str, Path]:
    return {
        "cover_1x1.png": make_cover(out_dir / "cover_1x1.png", 1080, 1080, title, artist, accent, base_image, seed, subtitle),
        "cover_9x16.png": make_cover(out_dir / "cover_9x16.png", 1080, 1920, title, artist, accent, base_image, seed, subtitle),
        "thumbnail_16x9.png": make_cover(out_dir / "thumbnail_16x9.png", 1920, 1080, title, artist, accent, base_image, seed, subtitle),
    }


def pwa_icons(static_dir: Path) -> None:
    for size in (192, 512):
        p = static_dir / f"icon-{size}.png"
        if p.exists():
            continue
        img = gradient_bg(size, size, "#37E5FF", "#8A5CFF", 3)
        triangle_mark(img, size // 2, size // 2, size // 4, "#37E5FF")
        img.save(p)
