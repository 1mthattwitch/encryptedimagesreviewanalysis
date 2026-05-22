"""
GPS map view: render an offline HTML file with photo location markers.
Uses folium (optional dep). Falls back to a static HTML table if unavailable.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


def _thumb_b64(path: Path, size: int = 80) -> str:
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        img.thumbnail((size, size))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def export_map(entries: list["FileEntry"], out_path: Path) -> Path:
    """
    Generate an HTML map file. Uses folium if available, else plain HTML table.
    """
    gps_entries = [e for e in entries if e.gps]
    if not gps_entries:
        out_path.write_text(
            "<html><body><h2>No GPS data found in scanned files.</h2></body></html>",
            encoding="utf-8",
        )
        return out_path

    try:
        import folium
        _export_folium(gps_entries, out_path)
    except ImportError:
        _export_plain_html(gps_entries, out_path)

    return out_path


def _export_folium(entries: list["FileEntry"], out_path: Path) -> None:
    import folium
    lats = [e.gps[0] for e in entries]
    lons = [e.gps[1] for e in entries]
    center = (sum(lats) / len(lats), sum(lons) / len(lons))

    m = folium.Map(location=center, zoom_start=12,
                   tiles="CartoDB dark_matter")

    for e in entries:
        thumb = _thumb_b64(e.path) if e.file_type == "image" else ""
        img_html = (f'<img src="data:image/jpeg;base64,{thumb}" '
                    f'width="80" style="border-radius:4px"><br>' if thumb else "")
        popup_html = (
            f'<div style="font-family:sans-serif;font-size:11px">'
            f'{img_html}'
            f'<b>{e.path.name}</b><br>'
            f'{e.ai_description or ""}<br>'
            f'{e.date.strftime("%Y-%m-%d") if e.date else ""}'
            f'</div>'
        )
        folium.Marker(
            location=[e.gps[0], e.gps[1]],
            popup=folium.Popup(popup_html, max_width=150),
            tooltip=e.path.name,
            icon=folium.Icon(color="red", icon="camera", prefix="fa"),
        ).add_to(m)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))


def _export_plain_html(entries: list["FileEntry"], out_path: Path) -> None:
    rows = []
    for e in entries:
        lat, lon = e.gps
        rows.append(
            f"<tr>"
            f"<td>{e.path.name}</td>"
            f"<td>{lat:.6f}</td><td>{lon:.6f}</td>"
            f"<td>{e.ai_description or ''}</td>"
            f"<td>{e.date.strftime('%Y-%m-%d') if e.date else ''}</td>"
            f"</tr>"
        )
    html = (
        "<html><head><title>GPS Locations</title>"
        "<style>body{background:#1a1a2e;color:#e0e0e0;font-family:sans-serif}"
        "table{border-collapse:collapse;width:100%}"
        "th{background:#16213e;padding:8px}td{padding:6px;border-bottom:1px solid #333}"
        "</style></head><body>"
        "<h2 style='color:#e94560'>📍 GPS Photo Locations</h2>"
        "<p style='color:#888'>Install folium for an interactive map: pip install folium</p>"
        "<table><tr><th>File</th><th>Lat</th><th>Lon</th>"
        "<th>Description</th><th>Date</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
