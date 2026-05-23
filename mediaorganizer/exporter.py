"""
Export scan results as JSON manifest, CSV spreadsheet, or self-contained HTML gallery.
"""

from __future__ import annotations

import base64
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


def _thumb_b64(path: Path, size: int = 120) -> str:
    try:
        from PIL import Image
        import io
        img = Image.open(path).convert("RGB")
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def export_json(entries: list["FileEntry"], out_path: Path) -> None:
    records = []
    for e in entries:
        records.append({
            "path": str(e.path),
            "type": e.file_type,
            "size_bytes": e.size_bytes,
            "date": e.date.isoformat() if e.date else None,
            "exif_date": e.exif_date.isoformat() if e.exif_date else None,
            "gps": list(e.gps) if e.gps else None,
            "camera": e.camera,
            "width": e.width,
            "height": e.height,
            "duration_s": e.duration_s,
            "ai_description": e.ai_description,
            "ai_category": e.ai_category,
            "proposed_name": e.proposed_name,
            "health_ok": e.health_ok,
            "health_issues": e.health_issues,
            "md5": e.md5,
            "quality_grade": e.quality_grade,
            "face_count": e.face_count,
            "ocr_text": e.ocr_text,
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "total": len(records),
        "files": records,
    }, indent=2))


def export_csv(entries: list["FileEntry"], out_path: Path) -> None:
    fields = [
        "path", "type", "size_bytes", "date", "exif_date",
        "gps_lat", "gps_lon", "camera", "width", "height",
        "duration_s", "ai_description", "ai_category",
        "proposed_name", "health_ok", "health_issues",
        "quality_grade", "face_count",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for e in entries:
            lat, lon = (e.gps or (None, None))
            w.writerow({
                "path": str(e.path),
                "type": e.file_type,
                "size_bytes": e.size_bytes,
                "date": e.date.isoformat() if e.date else "",
                "exif_date": e.exif_date.isoformat() if e.exif_date else "",
                "gps_lat": lat, "gps_lon": lon,
                "camera": e.camera or "",
                "width": e.width or "",
                "height": e.height or "",
                "duration_s": e.duration_s or "",
                "ai_description": e.ai_description or "",
                "ai_category": e.ai_category or "",
                "proposed_name": e.proposed_name or "",
                "health_ok": e.health_ok,
                "health_issues": "; ".join(e.health_issues),
                "quality_grade": e.quality_grade or "",
                "face_count": e.face_count if e.face_count is not None else "",
            })


def export_html(entries: list["FileEntry"], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gallery.html"

    cards_html = []
    for e in entries:
        if e.file_type == "image":
            thumb = _thumb_b64(e.path)
            img_tag = (f'<img src="data:image/jpeg;base64,{thumb}" '
                       f'class="thumb" loading="lazy">' if thumb else
                       '<div class="thumb nothumb">🖼</div>')
        elif e.file_type == "video":
            img_tag = '<div class="thumb nothumb">🎬</div>'
        elif e.file_type == "pdf":
            img_tag = '<div class="thumb nothumb">📄</div>'
        else:
            img_tag = '<div class="thumb nothumb">📁</div>'

        desc = e.ai_description or ""
        cat = e.ai_category or e.file_type
        date_str = e.date.strftime("%Y-%m-%d") if e.date else "—"
        size_mb = e.size_bytes / 1048576
        health = "✓" if e.health_ok else "⚠"
        grade = e.quality_grade or ""
        fname = e.path.name

        cards_html.append(f"""
        <div class="card" data-type="{e.file_type}" data-cat="{cat}">
          {img_tag}
          <div class="info">
            <div class="fname" title="{fname}">{fname}</div>
            <div class="meta">{cat} · {date_str} · {size_mb:.1f} MB {health}</div>
            <div class="desc">{desc}</div>
            {f'<div class="grade grade-{grade.lower()}">{grade}</div>' if grade else ''}
          </div>
        </div>""")

    categories = sorted({e.ai_category or e.file_type for e in entries})
    filter_buttons = "".join(
        f'<button onclick="filter(\'{c}\')">{c}</button>' for c in categories
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Media Organizer Gallery</title>
<style>
  body{{background:#1a1a2e;color:#e0e0e0;font-family:sans-serif;margin:0;padding:16px}}
  h1{{color:#e94560;margin-bottom:8px}}
  .filters{{margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap}}
  .filters button{{background:#16213e;color:#e0e0e0;border:1px solid #e94560;
    padding:4px 12px;border-radius:20px;cursor:pointer;font-size:12px}}
  .filters button:hover,.filters button.active{{background:#e94560;color:#fff}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}}
  .card{{background:#16213e;border-radius:8px;overflow:hidden;transition:transform .15s}}
  .card:hover{{transform:scale(1.03)}}
  .thumb{{width:100%;height:140px;object-fit:cover;display:block}}
  .nothumb{{display:flex;align-items:center;justify-content:center;
    font-size:40px;background:#0f3460;height:140px}}
  .info{{padding:8px}}
  .fname{{font-size:11px;font-weight:bold;white-space:nowrap;overflow:hidden;
    text-overflow:ellipsis;color:#e94560}}
  .meta{{font-size:10px;color:#888;margin:2px 0}}
  .desc{{font-size:11px;color:#bbb;margin-top:4px}}
  .grade{{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;margin-top:4px}}
  .grade-a,.grade-b{{background:#27ae60;color:#fff}}
  .grade-c{{background:#f39c12;color:#fff}}
  .grade-d,.grade-f{{background:#e74c3c;color:#fff}}
  #count{{color:#888;font-size:12px;margin-bottom:8px}}
</style>
</head>
<body>
<h1>📁 Media Gallery</h1>
<p id="count">{len(entries)} files</p>
<div class="filters">
  <button onclick="filter('all')" class="active">All</button>
  {filter_buttons}
</div>
<div class="grid" id="grid">
{''.join(cards_html)}
</div>
<script>
let active='all';
function filter(cat){{
  active=cat;
  document.querySelectorAll('.filters button').forEach(b=>
    b.classList.toggle('active',b.textContent===cat||(cat==='all'&&b.textContent==='All')));
  document.querySelectorAll('.card').forEach(c=>{{
    const show=cat==='all'||c.dataset.cat===cat||c.dataset.type===cat;
    c.style.display=show?'':'none';
  }});
  const vis=document.querySelectorAll('.card:not([style*="none"])').length;
  document.getElementById('count').textContent=vis+' files';
}}
</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    return out_path
