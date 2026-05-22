"""
Antivirus scanning: Windows Defender (MpCmdRun) and ClamAV (clamscan).
Results are stored on each FileEntry as health issues.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import FileEntry


def _find_defender() -> Optional[str]:
    paths = [
        r"C:\Program Files\Windows Defender\MpCmdRun.exe",
        r"C:\Program Files (x86)\Windows Defender\MpCmdRun.exe",
    ]
    for p in paths:
        if Path(p).is_file():
            return p
    return shutil.which("MpCmdRun")


def _find_clamav() -> Optional[str]:
    return shutil.which("clamscan")


def scan_file_defender(path: Path) -> Optional[str]:
    """Return threat name string if infected, None if clean or unavailable."""
    exe = _find_defender()
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "-Scan", "-ScanType", "3", "-File", str(path)],
            capture_output=True, timeout=30,
        )
        output = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
        if "Threat" in output or result.returncode not in (0, 2):
            # Extract threat name if present
            for line in output.splitlines():
                if "Threat" in line:
                    return line.strip()
            return "Threat detected"
    except Exception:
        pass
    return None


def scan_file_clamav(path: Path) -> Optional[str]:
    """Return threat name string if infected, None if clean or unavailable."""
    exe = _find_clamav()
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "--no-summary", str(path)],
            capture_output=True, timeout=30,
        )
        output = result.stdout.decode(errors="replace")
        if result.returncode == 1:  # infected
            for line in output.splitlines():
                if "FOUND" in line:
                    return line.strip()
            return "Infected"
    except Exception:
        pass
    return None


def scan_entry(entry: "FileEntry") -> Optional[str]:
    """Scan a single file with available AV engines. Returns threat string or None."""
    threat = scan_file_defender(entry.path)
    if threat is None:
        threat = scan_file_clamav(entry.path)
    if threat:
        entry.health_ok = False
        entry.health_issues.append(f"THREAT: {threat}")
    return threat


def scan_all(entries: list["FileEntry"], progress_cb=None) -> list["FileEntry"]:
    """Scan all entries. Returns list of infected entries."""
    infected = []
    total = len(entries)
    for i, entry in enumerate(entries):
        if scan_entry(entry):
            infected.append(entry)
        if progress_cb:
            progress_cb(i + 1, total)
    return infected
