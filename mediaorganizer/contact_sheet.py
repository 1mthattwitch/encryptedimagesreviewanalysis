"""
Generate a contact sheet (thumbnail grid) from a list of FileEntry objects.
Uses Pillow only — no extra deps.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .scanner import FileEntry

THUMB_SIZE = 200
LABEL_HEIGHT = 20
BG_COLOR = (26, 26, 46)
LABEL_BG = (22, 33, 62)
LABEL_FG = (200, 200, 200)


def make_contact_sheet(
    entries: list["FileEntry"],
    out_path: Path,
    cols: int = 6,
    thumb_px: int = THUMB_SIZE,
    title: Optional[str] = None,
) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    # Filter to images only (skip docs/audio/etc.)
    image_entries = [e for e in entries if e.file_type == "image"]
    if not image_entries:
        raise ValueError("No image entries to make contact sheet from")

    rows = (len(image_entries) + cols - 1) // cols
    cell_w = thumb_px
    cell_h = thumb_px + LABEL_HEIGHT
    header_h = 30 if title else 0
    sheet_w = cell_w * cols
    sheet_h = cell_h * rows + header_h

    sheet = Image.new("RGB", (sheet_w, sheet_h), color=BG_COLOR)
    draw = ImageDraw.Draw(sheet)

    # Try to load a small font, fall back to default
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        font = ImageFont.load_default()

    if title:
        draw.rectangle([(0, 0), (sheet_w, header_h)], fill=LABEL_BG)
        draw.text((8, 6), title, fill=(233, 69, 96), font=font)

    for idx, entry in enumerate(image_entries):
        row, col = divmod(idx, cols)
        x = col * cell_w
        y = row * cell_h + header_h

        # Thumbnail
        try:
            img = Image.open(entry.path).convert("RGB")
            img.thumbnail((thumb_px, thumb_px))
            # Centre on cell
            tx = x + (thumb_px - img.width) // 2
            ty = y + (thumb_px - img.height) // 2
            sheet.paste(img, (tx, ty))
        except Exception:
            draw.rectangle([(x, y), (x + thumb_px, y + thumb_px)], fill=(40, 40, 60))
            draw.text((x + 4, y + thumb_px // 2), "?", fill=(150, 150, 150), font=font)

        # Label
        label_y = y + thumb_px
        draw.rectangle([(x, label_y), (x + cell_w, label_y + LABEL_HEIGHT)], fill=LABEL_BG)
        name = entry.path.name
        if len(name) > 22:
            name = name[:19] + "…"
        draw.text((x + 3, label_y + 3), name, fill=LABEL_FG, font=font)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="JPEG", quality=85)
    return out_path
