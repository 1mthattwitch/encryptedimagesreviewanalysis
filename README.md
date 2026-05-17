# Media Organizer — Gallery Vault File Processor

A fully offline tool to export, analyze, rename, and organize your Gallery Vault photos, videos, and documents using local AI (Ollama).

## Quick Start

### Step 1 — Export from Gallery Vault

Double-click **`gallery_vault_export.bat`** and choose:

- **Option 1 (In-app export):** Use Gallery Vault's built-in Restore/Export feature, then copy files via USB. Step-by-step instructions are shown.
- **Option 2 (ADB pull):** Requires USB Debugging enabled on your phone. The script pulls files directly via ADB.

Files are saved to `GalleryVaultExport\` in the same folder as the script.

### Step 2 — Analyze and Organize

Double-click **`run.bat`**. It will:

1. Check Python is installed
2. Auto-update the tool from GitHub
3. Install required packages
4. Launch the graphical interface

In the GUI:
1. Click **Browse** and select `GalleryVaultExport\`
2. Choose an **organization mode** (Type / Date / Content)
3. Click **Scan & Analyze** — the tool checks every file for health issues, finds duplicates, and uses Ollama for AI descriptions
4. Review results in the file list and Preview tab
5. Tick **Apply moves**, then click **Apply All** to move and rename files

## Features

| Feature | Details |
|---|---|
| **Health check** | Detects corrupt/unreadable images, videos, PDFs, and documents |
| **Duplicate detection** | Exact (MD5) and near-duplicate (perceptual hash) for images and videos |
| **AI renaming** | Ollama vision models (moondream, llava, bakllava) describe each file in 5–10 words |
| **Organization modes** | By type (Images/Videos/PDFs), by date (YYYY/MM), or by AI content category |
| **Storage report** | Size breakdown, top-10 largest files, recoverable duplicate space |
| **Export** | JSON manifest, CSV spreadsheet, browsable HTML gallery with thumbnails |
| **Dry-run mode** | Preview all proposed moves before anything is touched |
| **100% offline** | No API keys, no cloud calls, no telemetry |

## Requirements

- **Python 3.9+** — https://www.python.org/downloads/ (tick "Add to PATH")
- **Ollama** (optional but recommended) — https://ollama.com/ — then pull a vision model:
  ```
  ollama pull moondream
  ```
  The tool works without Ollama; files are named from EXIF date/metadata.

## CLI Usage

```
python -m mediaorganizer.cli PATH [options]

Options:
  --apply              Execute moves (default: dry-run)
  --mode {type,date,content}  Organization mode
  --output DIR         Output directory (default: ./Organized)
  --check-health       Report unreadable files
  --find-duplicates    Detect exact and near-duplicate files
  --storage-report     Print size breakdown
  --analyze            Describe files with Ollama
  --export-manifest    Save JSON manifest
  --export-csv         Save CSV spreadsheet
  --export-gallery     Save browsable HTML gallery
  --ollama-host URL    Custom Ollama server (default: http://localhost:11434)
```

**Examples:**
```bash
# Quick health + storage check (no moves)
python -m mediaorganizer.cli ./GalleryVaultExport --check-health --storage-report

# Full analysis, organize by date, apply
python -m mediaorganizer.cli ./GalleryVaultExport --analyze --mode date --apply

# Find and report duplicates, export CSV
python -m mediaorganizer.cli ./GalleryVaultExport --find-duplicates --export-csv report.csv
```

## File Organization Modes

**Type mode** (default):
```
Organized/
├── Images/
├── Videos/
├── PDFs/
├── Documents/
├── Duplicates/
└── Unreadable/
```

**Date mode** (uses EXIF date or file modified time):
```
Organized/
├── Images/2024/05/
├── Videos/2023/12/
└── ...
```

**Content mode** (requires Ollama):
```
Organized/
├── People/
├── Selfies/
├── Landscapes/
├── Animals/
├── Food/
├── Screenshots/
├── Events/
├── Architecture/
└── Other/
```
