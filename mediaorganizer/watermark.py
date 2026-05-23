"""
Batch watermarking: text or logo overlay on images.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


def _apply_text_watermark(
    img, text: str, opacity: int = 128, position: str = "bottom-right"
):
    from PIL import ImageDraw, ImageFont, Image
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    try:
        font = ImageFont.truetype("arial.ttf", max(12, img.width // 40))
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = 10

    if position == "bottom-right":
        xy = (img.width - tw - margin, img.height - th - margin)
    elif position == "bottom-left":
        xy = (margin, img.height - th - margin)
    elif position == "top-right":
        xy = (img.width - tw - margin, margin)
    elif position == "top-left":
        xy = (margin, margin)
    else:
        xy = (img.width - tw - margin, img.height - th - margin)

    # Shadow
    draw.text((xy[0] + 1, xy[1] + 1), text, font=font, fill=(0, 0, 0, opacity))
    draw.text(xy, text, font=font, fill=(255, 255, 255, opacity))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _apply_logo_watermark(
    img, logo_path: Path, opacity: float = 0.6, position: str = "bottom-right",
    max_logo_frac: float = 0.2,
):
    from PIL import Image
    logo = Image.open(logo_path).convert("RGBA")
    max_w = int(img.width * max_logo_frac)
    max_h = int(img.height * max_logo_frac)
    logo.thumbnail((max_w, max_h))

    margin = 10
    if position == "bottom-right":
        xy = (img.width - logo.width - margin, img.height - logo.height - margin)
    elif position == "bottom-left":
        xy = (margin, img.height - logo.height - margin)
    elif position == "top-right":
        xy = (img.width - logo.width - margin, margin)
    else:
        xy = (margin, margin)

    # Apply opacity to logo
    r, g, b, a = logo.split()
    a = a.point(lambda v: int(v * opacity))
    logo.putalpha(a)

    base = img.convert("RGBA")
    base.paste(logo, xy, mask=logo)
    return base.convert("RGB")


def watermark_image(
    src: Path,
    dest: Optional[Path] = None,
    text: Optional[str] = None,
    logo: Optional[Path] = None,
    opacity: int = 128,
    position: str = "bottom-right",
) -> Path:
    from PIL import Image
    img = Image.open(src).convert("RGB")
    if text:
        img = _apply_text_watermark(img, text, opacity, position)
    if logo:
        img = _apply_logo_watermark(img, logo, opacity / 255, position)
    out = dest or src
    if out.suffix.lower() in (".jpg", ".jpeg"):
        img.save(out, format="JPEG", quality=92)
    else:
        img.save(out)
    return out


def batch_watermark(
    entries: list["FileEntry"],
    text: Optional[str] = None,
    logo: Optional[Path] = None,
    opacity: int = 128,
    position: str = "bottom-right",
    in_place: bool = True,
    out_dir: Optional[Path] = None,
) -> list[Path]:
    results = []
    for e in entries:
        if e.file_type != "image":
            continue
        if out_dir:
            dest = out_dir / e.path.name
            out_dir.mkdir(parents=True, exist_ok=True)
        else:
            dest = e.path if in_place else None
        try:
            out = watermark_image(e.path, dest, text, logo, opacity, position)
            results.append(out)
        except Exception:
            pass
    return results
