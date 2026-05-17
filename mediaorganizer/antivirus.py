"""Virus and spyware scanning via Windows Defender (built-in) or ClamAV."""
from __future__ import annotations

import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ScanResult:
    clean: bool
    engine: str          # 'defender', 'clamav', 'none'
    threat: str          # threat name if found, else ''
    error: str           # error message if scan failed


# ── Engine detection ───────────────────────────────────────────────────────────

_DEFENDER_PATHS = [
    r'C:\Program Files\Windows Defender\MpCmdRun.exe',
    r'C:\Program Files (x86)\Windows Defender\MpCmdRun.exe',
]


def _defender_exe() -> Optional[Path]:
    for p in _DEFENDER_PATHS:
        if Path(p).exists():
            return Path(p)
    return None


def _clamav_exe() -> Optional[str]:
    return shutil.which('clamscan')


def available_engine() -> str:
    """Return the best available scan engine: 'defender', 'clamav', or 'none'."""
    if _defender_exe():
        return 'defender'
    if _clamav_exe():
        return 'clamav'
    return 'none'


# ── Per-file scanning ────────────────────────────────────────────────────────────

def _scan_defender(path: Path) -> ScanResult:
    exe = _defender_exe()
    if not exe:
        return ScanResult(clean=True, engine='none', threat='', error='Defender not found')
    try:
        result = subprocess.run(
            [str(exe), '-Scan', '-ScanType', '3', '-File', str(path), '-DisableRemediation'],
            capture_output=True, text=True, timeout=60,
        )
        # Exit code 0 = clean, 2 = threat found
        if result.returncode == 0:
            return ScanResult(clean=True, engine='defender', threat='', error='')
        # Parse threat name from output
        threat = ''
        for line in result.stdout.splitlines():
            if 'threat' in line.lower() or 'detected' in line.lower():
                threat = line.strip()
                break
        return ScanResult(clean=False, engine='defender',
                          threat=threat or 'Threat detected', error='')
    except subprocess.TimeoutExpired:
        return ScanResult(clean=True, engine='defender', threat='',
                          error='Scan timed out')
    except Exception as exc:
        return ScanResult(clean=True, engine='defender', threat='', error=str(exc))


def _scan_clamav(path: Path) -> ScanResult:
    exe = _clamav_exe()
    if not exe:
        return ScanResult(clean=True, engine='none', threat='', error='ClamAV not found')
    try:
        result = subprocess.run(
            [exe, '--no-summary', str(path)],
            capture_output=True, text=True, timeout=60,
        )
        # Exit code 0 = clean, 1 = virus found, 2 = error
        if result.returncode == 0:
            return ScanResult(clean=True, engine='clamav', threat='', error='')
        if result.returncode == 1:
            threat = ''
            for line in result.stdout.splitlines():
                if 'FOUND' in line:
                    parts = line.rsplit(':', 1)
                    threat = parts[-1].replace('FOUND', '').strip() if len(parts) > 1 else line
                    break
            return ScanResult(clean=False, engine='clamav',
                              threat=threat or 'Threat detected', error='')
        return ScanResult(clean=True, engine='clamav', threat='',
                          error=result.stderr.strip()[:120])
    except subprocess.TimeoutExpired:
        return ScanResult(clean=True, engine='clamav', threat='',
                          error='Scan timed out')
    except Exception as exc:
        return ScanResult(clean=True, engine='clamav', threat='', error=str(exc))


def scan_file(path: Path, engine: str = '') -> ScanResult:
    """Scan a single file. Uses best available engine if engine not specified."""
    eng = engine or available_engine()
    if eng == 'defender':
        return _scan_defender(path)
    if eng == 'clamav':
        return _scan_clamav(path)
    return ScanResult(clean=True, engine='none', threat='',
                      error='No scan engine available (install ClamAV or enable Windows Defender)')


# ── Batch scanning ──────────────────────────────────────────────────────────────

from .scanner import FileEntry
from typing import Callable


def scan_entries(
    entries: list[FileEntry],
    engine: str = '',
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag=None,
) -> dict:
    """
    Scan all entries. Attaches results to each entry via entry.metadata['av_*'].
    Returns a summary dict.
    """
    eng = engine or available_engine()
    threats: list[FileEntry] = []
    errors: list[FileEntry] = []

    for i, entry in enumerate(entries):
        if cancel_flag and cancel_flag.is_set():
            break
        if progress_cb:
            progress_cb(i, len(entries), entry.path.name)

        result = scan_file(entry.path, eng)
        entry.metadata['av_clean'] = result.clean
        entry.metadata['av_engine'] = result.engine
        entry.metadata['av_threat'] = result.threat
        entry.metadata['av_error'] = result.error

        if not result.clean:
            threats.append(entry)
        if result.error:
            errors.append(entry)

    return {
        'engine': eng,
        'scanned': len(entries),
        'threats': len(threats),
        'threat_files': [{'path': str(e.path), 'threat': e.metadata.get('av_threat', '')}
                         for e in threats],
        'errors': len(errors),
    }
