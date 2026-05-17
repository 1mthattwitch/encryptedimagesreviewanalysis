"""Export results as JSON manifest, CSV spreadsheet, or HTML gallery."""
from __future__ import annotations

import base64
import csv
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

from .scanner import FileEntry


def _human(b: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024:
            return f'{int(b)}{unit}'
        b /= 1024
    return f'{int(b)}GB'


def _entry_dict(e: FileEntry) -> dict:
    return {
        'original_path': str(e.path),
        'proposed_name': e.proposed_name,
        'file_type': e.file_type,
        'size_bytes': e.size_bytes,
        'date': e.date.isoformat() if e.date else None,
        'health_ok': e.health_ok,
        'health_issues': '; '.join(e.health_issues),
        'is_duplicate': e.is_duplicate,
        'duplicate_group': e.duplicate_group,
        'ai_description': e.ai_description,
        'ai_category': e.ai_category,
        'content_hash': e.content_hash,
    }


def export_json(entries: list[FileEntry], report: dict, out_path: Path) -> None:
    data = {
        'generated_at': datetime.now().isoformat(),
        'totals': {
            'files': report.get('total_files', 0),
            'size_bytes': report.get('total_size_bytes', 0),
            'unhealthy': report.get('unhealthy_count', 0),
            'duplicates': report.get('duplicate_count', 0),
        },
        'files': [_entry_dict(e) for e in entries],
    }
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')


def export_csv(entries: list[FileEntry], out_path: Path) -> None:
    fieldnames = [
        'original_path', 'proposed_name', 'file_type', 'size_bytes',
        'date', 'health_ok', 'health_issues', 'is_duplicate',
        'ai_description', 'ai_category', 'content_hash',
    ]
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for e in entries:
            w.writerow(_entry_dict(e))


def _thumb_data_uri(e: FileEntry) -> str:
    if e.file_type != 'image':
        return ''
    try:
        from PIL import Image
        img = Image.open(e.path).convert('RGB')
        img.thumbnail((240, 240), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=72)
        return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''


def export_html(entries: list[FileEntry], report: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cards_html = []
    for e in entries:
        thumb = _thumb_data_uri(e)
        icon = {'image': '\U0001f5bc', 'video': '\U0001f4f9', 'pdf': '\U0001f4c4', 'document': '\U0001f4cb'}.get(e.file_type, '\U0001f4c1')
        status_sym = '✓' if e.health_ok else '✕'
        status_cls = 'ok' if e.health_ok else 'bad'
        dup_badge = '<span class="dup">⚠ dup</span>' if e.is_duplicate else ''
        if thumb:
            visual = f'<img src="{thumb}" alt="">'
        else:
            visual = f'<div class="no-thumb">{icon}</div>'
        cards_html.append(
            f'<div class="card" data-type="{e.file_type}" data-cat="{e.ai_category or ""}">'
            f'{visual}'
            f'<div class="info">'
            f'<div class="name" title="{e.path.name}">{e.path.name}</div>'
            f'<div class="meta">{e.file_type} &middot; {_human(e.size_bytes)} &middot; <span class="{status_cls}">{status_sym}</span>{dup_badge}</div>'
            f'<div class="desc">{e.ai_description or ""}</div>'
            f'<div class="proposed">&rarr; {e.proposed_name or ""}</div>'
            f'</div></div>'
        )

    total_files = report.get('total_files', len(entries))
    total_size = _human(report.get('total_size_bytes', 0))
    dup_groups = report.get('duplicate_groups', 0)
    issues = report.get('unhealthy_count', 0)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Media Organizer Gallery</title>
<style>
:root{{--bg:#1a1a2e;--card:#16213e;--card2:#0f3460;--accent:#e94560;--text:#eaeaea;--muted:#888;--green:#4caf50;--red:#f44336;--yellow:#ff9800}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:system-ui,sans-serif;padding:1.5rem}}
h1{{color:var(--accent);margin-bottom:.5rem;font-size:1.6rem}}
.summary{{color:var(--muted);font-size:.85rem;margin-bottom:1.2rem}}
.filters{{margin-bottom:1rem;display:flex;gap:.5rem;flex-wrap:wrap}}
.filters button{{background:var(--card);color:var(--text);border:1px solid #333;border-radius:20px;padding:.3rem 1rem;cursor:pointer;font-size:.85rem;transition:all .2s}}
.filters button.active,.filters button:hover{{background:var(--accent);border-color:var(--accent);color:#fff}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:1rem}}
.card{{background:var(--card);border-radius:10px;overflow:hidden;transition:transform .15s,box-shadow .15s;cursor:pointer}}
.card:hover{{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,.4)}}
.card img{{width:100%;height:155px;object-fit:cover;display:block}}
.no-thumb{{width:100%;height:155px;display:flex;align-items:center;justify-content:center;background:var(--card2);font-size:2.5rem}}
.info{{padding:.7rem}}
.name{{font-size:.72rem;font-family:monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--text)}}
.meta{{font-size:.65rem;color:var(--muted);margin-top:.25rem}}
.ok{{color:var(--green)}}.bad{{color:var(--red)}}
.dup{{color:var(--yellow);margin-left:.3rem}}
.desc{{font-size:.7rem;color:#aaa;margin-top:.3rem;font-style:italic;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.proposed{{font-size:.65rem;color:var(--accent);margin-top:.25rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
</style>
</head>
<body>
<h1>&#128193; Media Organizer Gallery</h1>
<p class="summary">{total_files:,} files &middot; {total_size} total &middot; {issues} issues &middot; {dup_groups} duplicate groups &middot; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div class="filters">
  <button class="active" onclick="filter(this,'all')">All ({total_files})</button>
  <button onclick="filter(this,'image')">&#128444; Images</button>
  <button onclick="filter(this,'video')">&#128249; Videos</button>
  <button onclick="filter(this,'pdf')">&#128196; PDFs</button>
  <button onclick="filter(this,'document')">&#128203; Docs</button>
  <button onclick="filter(this,'_dup')">&#9888; Duplicates</button>
  <button onclick="filter(this,'_bad')">&#10005; Issues</button>
</div>
<div class="grid" id="grid">{''.join(cards_html)}</div>
<script>
function filter(btn,type){{document.querySelectorAll('.filters button').forEach(b=>b.classList.remove('active'));btn.classList.add('active');document.querySelectorAll('.card').forEach(c=>{{let show=false;if(type==='all')show=true;else if(type==='_dup')show=c.querySelector('.dup')!==null;else if(type==='_bad')show=c.querySelector('.bad')!==null;else show=c.dataset.type===type;c.style.display=show?'':'none'}});}}
</script>
</body>
</html>"""
    (out_dir / 'index.html').write_text(html, encoding='utf-8')
