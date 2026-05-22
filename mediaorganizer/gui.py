"""
Dark-theme Tkinter GUI for mediaorganizer.
Tabs: Files | Preview | Duplicates | Events | Storage | Tools | Export
"""

from __future__ import annotations

import io
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# ── Colour palette ────────────────────────────────────────────────────────────
BG     = "#1a1a2e"
BG2    = "#16213e"
BG3    = "#0f3460"
ACCENT = "#e94560"
FG     = "#e0e0e0"
FG2    = "#aaaaaa"
GREEN  = "#27ae60"
YELLOW = "#f39c12"
RED    = "#e74c3c"
MONO   = ("Consolas", 10) if sys.platform == "win32" else ("DejaVu Sans Mono", 10)


def _style(root: tk.Tk):
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=FG, fieldbackground=BG2,
                 troughcolor=BG2, selectbackground=BG3, selectforeground=FG,
                 bordercolor=BG3, lightcolor=BG2, darkcolor=BG)
    s.configure("TNotebook", background=BG, borderwidth=0)
    s.configure("TNotebook.Tab", background=BG2, foreground=FG2,
                 padding=(12, 6), borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", BG3)],
          foreground=[("selected", FG)])
    s.configure("TFrame", background=BG)
    s.configure("TLabel", background=BG, foreground=FG)
    s.configure("TButton", background=BG3, foreground=FG,
                 borderwidth=1, relief="flat", padding=(10, 5))
    s.map("TButton", background=[("active", ACCENT)])
    s.configure("Accent.TButton", background=ACCENT, foreground="white",
                 font=("Segoe UI", 10, "bold"))
    s.map("Accent.TButton", background=[("active", "#c0392b")])
    s.configure("TEntry", fieldbackground=BG2, foreground=FG, bordercolor=BG3,
                 insertcolor=FG)
    s.configure("TCombobox", fieldbackground=BG2, foreground=FG, background=BG2,
                 arrowcolor=FG)
    s.configure("Vertical.TScrollbar", background=BG2, troughcolor=BG,
                 arrowcolor=FG2)
    s.configure("TProgressbar", background=ACCENT, troughcolor=BG2)
    s.configure("Treeview", background=BG2, foreground=FG,
                 fieldbackground=BG2, borderwidth=0, rowheight=22)
    s.configure("Treeview.Heading", background=BG3, foreground=FG,
                 borderwidth=0)
    s.map("Treeview", background=[("selected", BG3)])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _human(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


def _grade_color(grade: Optional[str]) -> str:
    return {None: FG2, "A": GREEN, "B": GREEN, "C": YELLOW, "D": RED, "F": RED}.get(grade, FG2)


# ── Main application ──────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Organizer")
        self.geometry("1200x750")
        self.configure(bg=BG)
        _style(self)

        self._entries: list = []
        self._dup_groups: list = []
        self._event_groups: list = []
        self._scan_folder: Optional[Path] = None
        self._watcher = None
        self._selected_entry = None
        self._filter_var = tk.StringVar()
        self._quality_filter_var = tk.StringVar(value="All")
        self._mode_var = tk.StringVar(value="type")
        self._recursive_var = tk.BooleanVar(value=True)
        self._apply_var = tk.BooleanVar(value=False)
        self._output_var = tk.StringVar(value=str(Path.home() / "Organized"))

        self._build_toolbar()
        self._build_main()
        self._build_status()

    # ── Toolbar ───────────────────────────────────────────────────────────────

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=BG3, height=50)
        tb.pack(fill="x", side="top")
        tb.pack_propagate(False)

        tk.Label(tb, text="📁 Media Organizer", bg=BG3, fg=ACCENT,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=12, pady=8)

        # Folder picker
        self._folder_var = tk.StringVar(value="No folder selected")
        tk.Button(tb, text="Browse…", bg=BG2, fg=FG, relief="flat",
                  command=self._browse).pack(side="left", padx=4)
        tk.Label(tb, textvariable=self._folder_var, bg=BG3, fg=FG2,
                 font=MONO).pack(side="left", padx=4)

        # Recursive
        tk.Checkbutton(tb, text="Recursive", variable=self._recursive_var,
                       bg=BG3, fg=FG, selectcolor=BG2,
                       activebackground=BG3).pack(side="left", padx=4)

        # Mode
        tk.Label(tb, text="Mode:", bg=BG3, fg=FG2).pack(side="left", padx=(12, 2))
        mode_cb = ttk.Combobox(tb, textvariable=self._mode_var,
                               values=["type", "date", "content", "event"],
                               width=8, state="readonly")
        mode_cb.pack(side="left", padx=2)

        # Scan
        self._scan_btn = tk.Button(tb, text="⟳ Scan", bg=ACCENT, fg="white",
                                   font=("Segoe UI", 10, "bold"), relief="flat",
                                   padx=12, command=self._scan)
        self._scan_btn.pack(side="left", padx=8)

        # Watch toggle
        self._watch_btn = tk.Button(tb, text="👁 Watch", bg=BG2, fg=FG,
                                    relief="flat", padx=8,
                                    command=self._toggle_watch)
        self._watch_btn.pack(side="left", padx=4)

        # Ollama status
        self._ollama_label = tk.Label(tb, text="● Ollama", bg=BG3, fg=RED,
                                      font=("Segoe UI", 9))
        self._ollama_label.pack(side="right", padx=12)
        self.after(500, self._check_ollama)

    # ── Main panes ────────────────────────────────────────────────────────────

    def _build_main(self):
        pw = tk.PanedWindow(self, orient="horizontal", bg=BG,
                            sashwidth=4, sashrelief="flat")
        pw.pack(fill="both", expand=True)

        # Left: file list
        left = tk.Frame(pw, bg=BG, width=380)
        pw.add(left, minsize=260)
        self._build_file_list(left)

        # Right: tabs
        right = tk.Frame(pw, bg=BG)
        pw.add(right, minsize=400)
        self._notebook = ttk.Notebook(right)
        self._notebook.pack(fill="both", expand=True)

        self._tab_preview   = tk.Frame(self._notebook, bg=BG)
        self._tab_dupes     = tk.Frame(self._notebook, bg=BG)
        self._tab_events    = tk.Frame(self._notebook, bg=BG)
        self._tab_storage   = tk.Frame(self._notebook, bg=BG)
        self._tab_tools     = tk.Frame(self._notebook, bg=BG)
        self._tab_export    = tk.Frame(self._notebook, bg=BG)

        self._notebook.add(self._tab_preview, text="Preview")
        self._notebook.add(self._tab_dupes,   text="Duplicates")
        self._notebook.add(self._tab_events,  text="Events")
        self._notebook.add(self._tab_storage, text="Storage")
        self._notebook.add(self._tab_tools,   text="Tools")
        self._notebook.add(self._tab_export,  text="Export")

        self._build_preview_tab()
        self._build_dupes_tab()
        self._build_events_tab()
        self._build_storage_tab()
        self._build_tools_tab()
        self._build_export_tab()

    def _build_file_list(self, parent):
        # Filter bar
        fb = tk.Frame(parent, bg=BG2)
        fb.pack(fill="x", padx=4, pady=4)
        tk.Label(fb, text="Filter:", bg=BG2, fg=FG2).pack(side="left", padx=4)
        fe = tk.Entry(fb, textvariable=self._filter_var, bg=BG2, fg=FG,
                      insertbackground=FG, relief="flat")
        fe.pack(side="left", fill="x", expand=True)
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        tk.Label(fb, text="Grade:", bg=BG2, fg=FG2).pack(side="left", padx=(8, 2))
        qf = ttk.Combobox(fb, textvariable=self._quality_filter_var,
                          values=["All", "A", "B", "C", "D", "F"],
                          width=4, state="readonly")
        qf.pack(side="left")
        self._quality_filter_var.trace_add("write", lambda *_: self._apply_filter())

        # Treeview
        cols = ("name", "type", "size", "date", "grade", "status")
        self._tree = ttk.Treeview(parent, columns=cols, show="headings",
                                   selectmode="extended")
        self._tree.heading("name",   text="Name")
        self._tree.heading("type",   text="Type")
        self._tree.heading("size",   text="Size")
        self._tree.heading("date",   text="Date")
        self._tree.heading("grade",  text="Q")
        self._tree.heading("status", text="Status")
        self._tree.column("name",   width=160, stretch=True)
        self._tree.column("type",   width=60,  anchor="center")
        self._tree.column("size",   width=60,  anchor="e")
        self._tree.column("date",   width=80,  anchor="center")
        self._tree.column("grade",  width=30,  anchor="center")
        self._tree.column("status", width=50,  anchor="center")

        # tag colours
        self._tree.tag_configure("grade_a", foreground=GREEN)
        self._tree.tag_configure("grade_b", foreground=GREEN)
        self._tree.tag_configure("grade_c", foreground=YELLOW)
        self._tree.tag_configure("grade_d", foreground=RED)
        self._tree.tag_configure("grade_f", foreground=RED)
        self._tree.tag_configure("unhealthy", foreground=RED)

        vsb = ttk.Scrollbar(parent, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4)

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", self._on_double_click)

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_preview_tab(self):
        p = self._tab_preview
        # Image canvas
        self._canvas = tk.Canvas(p, bg=BG3, height=320, highlightthickness=0)
        self._canvas.pack(fill="x", padx=8, pady=(8, 4))
        # Buttons
        btn_row = tk.Frame(p, bg=BG)
        btn_row.pack(fill="x", padx=8)
        tk.Button(btn_row, text="🔍 Lightbox", bg=BG2, fg=FG, relief="flat",
                  command=self._open_lightbox).pack(side="left", padx=2)
        tk.Button(btn_row, text="✏ Review Renames", bg=BG2, fg=FG, relief="flat",
                  command=self._open_rename_preview).pack(side="left", padx=2)
        tk.Button(btn_row, text="↻ Rotate", bg=BG2, fg=FG, relief="flat",
                  command=self._rotate_current).pack(side="left", padx=2)

        # Metadata labels
        self._preview_info = tk.Text(p, height=6, bg=BG2, fg=FG2,
                                     relief="flat", font=MONO, state="disabled")
        self._preview_info.pack(fill="x", padx=8, pady=4)
        # AI description
        tk.Label(p, text="AI Description:", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8)
        self._desc_var = tk.StringVar()
        self._desc_entry = tk.Entry(p, textvariable=self._desc_var, bg=BG2, fg=FG,
                                    insertbackground=FG, relief="flat", font=MONO)
        self._desc_entry.pack(fill="x", padx=8, pady=2)
        # Proposed name
        tk.Label(p, text="Proposed Name:", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8)
        self._proposed_var = tk.StringVar()
        tk.Entry(p, textvariable=self._proposed_var, bg=BG2, fg=FG,
                 insertbackground=FG, relief="flat", font=MONO).pack(fill="x", padx=8, pady=2)
        # OCR text
        tk.Label(p, text="OCR Text:", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8)
        self._ocr_text = tk.Text(p, height=3, bg=BG2, fg=FG2,
                                  relief="flat", font=MONO, state="disabled")
        self._ocr_text.pack(fill="x", padx=8, pady=2)
        # Transcript
        tk.Label(p, text="Transcript:", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8)
        self._transcript_text = tk.Text(p, height=3, bg=BG2, fg=FG2,
                                         relief="flat", font=MONO, state="disabled")
        self._transcript_text.pack(fill="x", padx=8, pady=(2, 8))

    def _build_dupes_tab(self):
        p = self._tab_dupes
        tk.Label(p, text="Duplicate Groups", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(padx=8, pady=(8, 4), anchor="w")
        self._dupe_info_label = tk.Label(p, text="Run scan to detect duplicates",
                                          bg=BG, fg=FG2)
        self._dupe_info_label.pack(anchor="w", padx=8)

        cols = ("kind", "count", "wasted", "keep")
        self._dupe_tree = ttk.Treeview(p, columns=cols, show="headings")
        self._dupe_tree.heading("kind",   text="Type")
        self._dupe_tree.heading("count",  text="Files")
        self._dupe_tree.heading("wasted", text="Wasted")
        self._dupe_tree.heading("keep",   text="Keep")
        self._dupe_tree.column("kind",   width=70)
        self._dupe_tree.column("count",  width=50, anchor="center")
        self._dupe_tree.column("wasted", width=80, anchor="e")
        self._dupe_tree.column("keep",   width=200)
        vsb = ttk.Scrollbar(p, orient="vertical", command=self._dupe_tree.yview)
        self._dupe_tree.configure(yscrollcommand=vsb.set)
        self._dupe_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4)

    def _build_events_tab(self):
        p = self._tab_events
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(hdr, text="Photo Events", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(hdr, text="⚙ Gap (min):", bg=BG, fg=FG2,
                  relief="flat").pack(side="right", padx=2)
        self._gap_var = tk.StringVar(value="60")
        tk.Entry(hdr, textvariable=self._gap_var, width=5,
                 bg=BG2, fg=FG, relief="flat").pack(side="right")
        tk.Button(hdr, text="↺ Regroup", bg=BG2, fg=FG, relief="flat",
                  command=self._regroup_events).pack(side="right", padx=4)

        cols = ("name", "count", "start", "end")
        self._event_tree = ttk.Treeview(p, columns=cols, show="headings")
        self._event_tree.heading("name",  text="Event")
        self._event_tree.heading("count", text="Photos")
        self._event_tree.heading("start", text="Start")
        self._event_tree.heading("end",   text="End")
        self._event_tree.column("name",  width=250, stretch=True)
        self._event_tree.column("count", width=60,  anchor="center")
        self._event_tree.column("start", width=100, anchor="center")
        self._event_tree.column("end",   width=100, anchor="center")
        vsb2 = ttk.Scrollbar(p, orient="vertical", command=self._event_tree.yview)
        self._event_tree.configure(yscrollcommand=vsb2.set)
        self._event_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=4)
        vsb2.pack(side="right", fill="y", pady=4)

        tk.Button(p, text="📂 Organise by Event", bg=ACCENT, fg="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  command=self._organise_by_event).pack(pady=6)

    def _build_storage_tab(self):
        p = self._tab_storage
        tk.Label(p, text="Storage Breakdown", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(padx=8, pady=(8, 4), anchor="w")

        self._storage_canvas = tk.Canvas(p, bg=BG2, height=180,
                                          highlightthickness=0)
        self._storage_canvas.pack(fill="x", padx=8, pady=4)

        tk.Label(p, text="Top 10 Largest Files:", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8)
        cols = ("path", "size")
        self._top10_tree = ttk.Treeview(p, columns=cols, show="headings", height=8)
        self._top10_tree.heading("path", text="File")
        self._top10_tree.heading("size", text="Size")
        self._top10_tree.column("path", width=350, stretch=True)
        self._top10_tree.column("size", width=80, anchor="e")
        self._top10_tree.pack(fill="x", padx=8, pady=4)

    def _build_tools_tab(self):
        p = self._tab_tools
        canvas = tk.Canvas(p, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(p, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        def section(label):
            tk.Label(inner, text=label, bg=BG, fg=ACCENT,
                     font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
            sep = tk.Frame(inner, bg=BG3, height=1)
            sep.pack(fill="x", padx=8, pady=2)

        def tool_row(text, cmd, note=""):
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", padx=12, pady=2)
            tk.Button(row, text=text, bg=BG2, fg=FG, relief="flat",
                      command=cmd, padx=8).pack(side="left")
            if note:
                tk.Label(row, text=note, bg=BG, fg=FG2,
                         font=("Segoe UI", 8)).pack(side="left", padx=6)
            return row

        # Image tools
        section("🖼 Image Tools")
        tool_row("HEIC → JPG (batch)",      self._tool_heic_convert)
        tool_row("Fix EXIF Rotation",        self._tool_fix_rotation)
        tool_row("Strip GPS Metadata",       self._tool_strip_gps)
        tool_row("Strip ALL Metadata",       self._tool_strip_all)
        tool_row("Auto-Enhance",             self._tool_auto_enhance)
        tool_row("Blur Faces",               self._tool_blur_faces)
        tool_row("Remove Background",        self._tool_remove_bg, "(needs: pip install rembg)")
        tool_row("Run OCR",                  self._tool_run_ocr,   "(needs: Tesseract)")

        # Format convert row
        row_fmt = tk.Frame(inner, bg=BG)
        row_fmt.pack(fill="x", padx=12, pady=2)
        tk.Label(row_fmt, text="Convert:", bg=BG, fg=FG).pack(side="left")
        self._src_ext_var = tk.StringVar(value="heic")
        self._dst_ext_var = tk.StringVar(value="jpg")
        ext_vals = ["jpg", "jpeg", "png", "webp", "bmp", "tiff", "heic"]
        ttk.Combobox(row_fmt, textvariable=self._src_ext_var,
                     values=ext_vals, width=6, state="readonly").pack(side="left", padx=4)
        tk.Label(row_fmt, text="→", bg=BG, fg=FG).pack(side="left")
        ttk.Combobox(row_fmt, textvariable=self._dst_ext_var,
                     values=ext_vals, width=6, state="readonly").pack(side="left", padx=4)
        tk.Button(row_fmt, text="Convert", bg=BG2, fg=FG, relief="flat",
                  command=self._tool_batch_convert).pack(side="left", padx=4)

        # Batch resize row
        row_rsz = tk.Frame(inner, bg=BG)
        row_rsz.pack(fill="x", padx=12, pady=2)
        tk.Label(row_rsz, text="Resize max px:", bg=BG, fg=FG).pack(side="left")
        self._max_px_var = tk.StringVar(value="1920")
        tk.Entry(row_rsz, textvariable=self._max_px_var, width=6,
                 bg=BG2, fg=FG, relief="flat").pack(side="left", padx=4)
        tk.Button(row_rsz, text="Resize", bg=BG2, fg=FG, relief="flat",
                  command=self._tool_batch_resize).pack(side="left")

        # Quality score
        tool_row("Score Image Quality",  self._tool_score_quality)
        tool_row("Detect Faces",         self._tool_detect_faces)

        # Watermark row
        section("🖊 Watermark")
        row_wm = tk.Frame(inner, bg=BG)
        row_wm.pack(fill="x", padx=12, pady=2)
        tk.Label(row_wm, text="Text:", bg=BG, fg=FG).pack(side="left")
        self._wm_text_var = tk.StringVar()
        tk.Entry(row_wm, textvariable=self._wm_text_var, width=20,
                 bg=BG2, fg=FG, relief="flat").pack(side="left", padx=4)
        tk.Button(row_wm, text="Apply Watermark", bg=BG2, fg=FG, relief="flat",
                  command=self._tool_watermark).pack(side="left", padx=4)

        # Video tools
        section("🎬 Video Tools")
        tool_row("Compress Video",       self._tool_compress_video)
        tool_row("Convert to MP4",       self._tool_convert_mp4)

        # Trim row
        row_trim = tk.Frame(inner, bg=BG)
        row_trim.pack(fill="x", padx=12, pady=2)
        tk.Label(row_trim, text="Trim:", bg=BG, fg=FG).pack(side="left")
        self._trim_start_var = tk.StringVar(value="0")
        self._trim_end_var   = tk.StringVar(value="30")
        tk.Label(row_trim, text="start:", bg=BG, fg=FG2).pack(side="left", padx=(6, 2))
        tk.Entry(row_trim, textvariable=self._trim_start_var, width=6,
                 bg=BG2, fg=FG, relief="flat").pack(side="left")
        tk.Label(row_trim, text="end (s):", bg=BG, fg=FG2).pack(side="left", padx=(4, 2))
        tk.Entry(row_trim, textvariable=self._trim_end_var, width=6,
                 bg=BG2, fg=FG, relief="flat").pack(side="left")
        tk.Button(row_trim, text="Trim", bg=BG2, fg=FG, relief="flat",
                  command=self._tool_trim_video).pack(side="left", padx=4)

        # Audio extract
        row_aud = tk.Frame(inner, bg=BG)
        row_aud.pack(fill="x", padx=12, pady=2)
        tk.Label(row_aud, text="Extract Audio:", bg=BG, fg=FG).pack(side="left")
        self._audio_fmt_var = tk.StringVar(value="mp3")
        ttk.Combobox(row_aud, textvariable=self._audio_fmt_var,
                     values=["mp3", "aac", "wav", "flac"], width=6,
                     state="readonly").pack(side="left", padx=4)
        tk.Button(row_aud, text="Extract", bg=BG2, fg=FG, relief="flat",
                  command=self._tool_extract_audio).pack(side="left")

        tool_row("Video → GIF",          self._tool_video_gif)
        tool_row("Video Thumbnail Sheet", self._tool_video_sheet)
        tool_row("Merge Selected Videos", self._tool_merge_videos)

        # Transcribe
        row_trans = tk.Frame(inner, bg=BG)
        row_trans.pack(fill="x", padx=12, pady=2)
        tk.Label(row_trans, text="Transcribe Videos:", bg=BG, fg=FG).pack(side="left")
        self._whisper_model_var = tk.StringVar(value="tiny")
        ttk.Combobox(row_trans, textvariable=self._whisper_model_var,
                     values=["tiny", "base", "small"], width=7,
                     state="readonly").pack(side="left", padx=4)
        tk.Button(row_trans, text="Transcribe",
                  bg=BG2, fg=FG, relief="flat",
                  command=self._tool_transcribe).pack(side="left",
                  text="(needs: pip install openai-whisper)")

        # Organisation
        section("📂 Organisation")
        tool_row("Sort WhatsApp / Telegram / Screenshots", self._tool_app_sort)
        tool_row("Fix File Timestamps from EXIF",          self._tool_fix_timestamps)
        tool_row("Find Corrupted Files",                   self._tool_find_corrupt)
        tool_row("Find Stale Files (old, no EXIF)",        self._tool_find_stale)

        # Undo
        section("↩ Safety")
        tool_row("Undo Last Organise Run",  self._tool_undo)
        tool_row("Secure Delete Selected",  self._tool_secure_delete)

    def _build_export_tab(self):
        p = self._tab_export
        tk.Label(p, text="Export", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(padx=8, pady=(8, 4), anchor="w")

        def btn(text, cmd, desc=""):
            row = tk.Frame(p, bg=BG)
            row.pack(fill="x", padx=12, pady=4)
            tk.Button(row, text=text, bg=BG2, fg=FG, relief="flat",
                      padx=10, command=cmd).pack(side="left")
            if desc:
                tk.Label(row, text=desc, bg=BG, fg=FG2,
                         font=("Segoe UI", 8)).pack(side="left", padx=8)

        # Output folder
        row_out = tk.Frame(p, bg=BG)
        row_out.pack(fill="x", padx=12, pady=4)
        tk.Label(row_out, text="Output folder:", bg=BG, fg=FG).pack(side="left")
        tk.Entry(row_out, textvariable=self._output_var, bg=BG2, fg=FG,
                 relief="flat", width=35).pack(side="left", padx=4)
        tk.Button(row_out, text="…", bg=BG2, fg=FG, relief="flat",
                  command=self._pick_output).pack(side="left")

        tk.Frame(p, bg=BG3, height=1).pack(fill="x", padx=8, pady=6)

        btn("📋 Organise Files", self._organise,
            "Move files into folders by selected mode")

        row_apply = tk.Frame(p, bg=BG)
        row_apply.pack(fill="x", padx=12, pady=2)
        tk.Checkbutton(row_apply, text="Apply (execute moves — otherwise dry-run only)",
                       variable=self._apply_var, bg=BG, fg=FG,
                       selectcolor=BG2, activebackground=BG).pack(side="left")

        tk.Frame(p, bg=BG3, height=1).pack(fill="x", padx=8, pady=6)

        btn("📦 Export JSON Manifest",    self._export_json)
        btn("📊 Export CSV Spreadsheet",  self._export_csv)
        btn("🌐 Export HTML Gallery",     self._export_html,
            "Self-contained, opens in any browser")
        btn("📍 Export GPS Map",          self._export_map,
            "Needs GPS data in EXIF; folium optional")
        btn("🖼 Contact Sheet",           self._export_contact_sheet,
            "Thumbnail grid of all images")

        tk.Frame(p, bg=BG3, height=1).pack(fill="x", padx=8, pady=6)
        btn("📅 Calendar Heat Map",       self._export_calendar)

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status(self):
        sb = tk.Frame(self, bg=BG2, height=28)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(sb, textvariable=self._status_var, bg=BG2, fg=FG2,
                 font=("Segoe UI", 9)).pack(side="left", padx=8, pady=4)
        self._progress = ttk.Progressbar(sb, length=200, mode="determinate")
        self._progress.pack(side="right", padx=8, pady=4)
        self._count_label = tk.Label(sb, text="", bg=BG2, fg=FG2,
                                      font=("Segoe UI", 9))
        self._count_label.pack(side="right", padx=8)

    def _set_status(self, msg: str, progress: float = 0.0):
        self._status_var.set(msg)
        self._progress["value"] = progress * 100
        self.update_idletasks()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _browse(self):
        folder = filedialog.askdirectory(title="Select media folder")
        if folder:
            self._scan_folder = Path(folder)
            short = str(self._scan_folder)
            if len(short) > 60:
                short = "…" + short[-57:]
            self._folder_var.set(short)

    def _pick_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self._output_var.set(folder)

    def _check_ollama(self):
        def _check():
            from . import analyzer
            ok = analyzer.is_available()
            color = GREEN if ok else RED
            text = "● Ollama ✓" if ok else "● Ollama ✗"
            self.after(0, lambda: self._ollama_label.configure(fg=color, text=text))
        threading.Thread(target=_check, daemon=True).start()
        self.after(30000, self._check_ollama)

    def _scan(self):
        if not self._scan_folder:
            self._browse()
            if not self._scan_folder:
                return
        self._set_status("Scanning…", 0.1)
        self._scan_btn.configure(state="disabled")

        def _work():
            from . import scanner, health, duplicates, quality as qmod, events
            self.after(0, lambda: self._set_status("Discovering files…", 0.15))
            entries = scanner.scan(self._scan_folder,
                                   recursive=self._recursive_var.get())
            self.after(0, lambda: self._set_status(f"Health-checking {len(entries)} files…", 0.3))
            health.check_all(entries)
            self.after(0, lambda: self._set_status("Scoring quality…", 0.5))
            qmod.score_all(entries)
            self.after(0, lambda: self._set_status("Finding duplicates…", 0.65))
            dup_groups = duplicates.find_duplicates(entries)
            self.after(0, lambda: self._set_status("Grouping events…", 0.8))
            ev_groups = events.group_by_events(entries)
            self.after(0, lambda: self._finish_scan(entries, dup_groups, ev_groups))

        threading.Thread(target=_work, daemon=True).start()

    def _finish_scan(self, entries, dup_groups, ev_groups):
        self._entries = entries
        self._dup_groups = dup_groups
        self._event_groups = ev_groups
        self._populate_tree(entries)
        self._populate_dupes(dup_groups)
        self._populate_events(ev_groups)
        self._populate_storage(entries)
        n = len(entries)
        bad = sum(1 for e in entries if not e.health_ok)
        self._count_label.configure(
            text=f"{n} files  |  {len(dup_groups)} dup groups  |  {bad} unhealthy")
        self._set_status("Scan complete", 1.0)
        self._scan_btn.configure(state="normal")
        self.after(2000, lambda: self._set_status("Ready"))

    def _populate_tree(self, entries):
        self._tree.delete(*self._tree.get_children())
        for e in entries:
            grade = e.quality_grade or ""
            date_str = e.date.strftime("%Y-%m-%d") if e.date else ""
            status = "✓" if e.health_ok else "⚠"
            tags = []
            if e.quality_grade:
                tags.append(f"grade_{e.quality_grade.lower()}")
            if not e.health_ok:
                tags.append("unhealthy")
            self._tree.insert("", "end",
                               values=(e.path.name, e.file_type,
                                       _human(e.size_bytes), date_str,
                                       grade, status),
                               iid=str(id(e)),
                               tags=tuple(tags))
        # Attach entry reference map
        self._entry_map = {str(id(e)): e for e in entries}

    def _apply_filter(self):
        text = self._filter_var.get().lower()
        grade_filter = self._quality_filter_var.get()
        for iid, entry in self._entry_map.items() if hasattr(self, "_entry_map") else []:
            show = True
            if text and text not in entry.path.name.lower():
                if not (entry.ai_description and text in entry.ai_description.lower()):
                    if not (entry.ocr_text and text in entry.ocr_text.lower()):
                        show = False
            if grade_filter != "All" and entry.quality_grade != grade_filter:
                show = False
            # Tkinter Treeview doesn't have hide — detach/reattach
            if show:
                try:
                    self._tree.reattach(iid, "", "end")
                except Exception:
                    pass
            else:
                try:
                    self._tree.detach(iid)
                except Exception:
                    pass

    def _populate_dupes(self, groups):
        self._dupe_tree.delete(*self._dupe_tree.get_children())
        total_wasted = sum(g.wasted_bytes for g in groups)
        from . import reporter as rep
        self._dupe_info_label.configure(
            text=f"{len(groups)} groups  |  {rep._human(total_wasted)} recoverable")
        for g in groups:
            self._dupe_tree.insert("", "end", values=(
                g.kind, len(g.entries),
                rep._human(g.wasted_bytes),
                g.keep.path.name,
            ))

    def _populate_events(self, groups):
        self._event_tree.delete(*self._event_tree.get_children())
        for g in groups:
            start_str = g.start.strftime("%Y-%m-%d") if g.start.year > 1970 else "—"
            end_str   = g.end.strftime("%Y-%m-%d")   if g.end.year   > 1970 else "—"
            self._event_tree.insert("", "end", values=(
                g.display_name, len(g.entries), start_str, end_str))

    def _populate_storage(self, entries):
        from . import reporter as rep
        sr = rep.storage_report(entries)
        # Bar chart on canvas
        c = self._storage_canvas
        c.delete("all")
        cw = c.winfo_width() or 500
        ch = 180
        types = list(sr["by_type"].items())
        if not types:
            return
        max_bytes = max(t[1]["bytes"] for t in types) or 1
        colors = [ACCENT, "#3498db", GREEN, YELLOW, "#9b59b6", "#1abc9c"]
        bar_w = max(20, (cw - 60) // max(len(types), 1))
        for i, (ftype, info) in enumerate(types):
            bh = int((info["bytes"] / max_bytes) * (ch - 40))
            x = 30 + i * (bar_w + 4)
            color = colors[i % len(colors)]
            c.create_rectangle(x, ch - bh - 20, x + bar_w, ch - 20,
                                fill=color, outline="")
            c.create_text(x + bar_w // 2, ch - 10, text=ftype[:6],
                          fill=FG2, font=("Segoe UI", 8))
            c.create_text(x + bar_w // 2, ch - bh - 30, text=info["human"],
                          fill=FG, font=("Segoe UI", 7))

        # Top 10
        self._top10_tree.delete(*self._top10_tree.get_children())
        for item in sr["top10_largest"]:
            name = Path(item["path"]).name
            self._top10_tree.insert("", "end", values=(name, item["human"]))

    def _on_select(self, _event=None):
        sel = self._tree.selection()
        if not sel:
            return
        entry = getattr(self, "_entry_map", {}).get(sel[0])
        if not entry:
            return
        self._selected_entry = entry
        self._show_preview(entry)

    def _show_preview(self, entry):
        # Image
        self._canvas.delete("all")
        if entry.file_type == "image":
            try:
                from PIL import Image, ImageTk
                img = Image.open(entry.path)
                cw = max(self._canvas.winfo_width(), 400)
                img.thumbnail((cw, 300))
                self._preview_img = ImageTk.PhotoImage(img)
                self._canvas.configure(height=img.height)
                self._canvas.create_image(cw // 2, img.height // 2,
                                           image=self._preview_img, anchor="center")
            except Exception:
                self._canvas.create_text(200, 80, text="(preview unavailable)",
                                          fill=FG2)
        elif entry.file_type == "video":
            self._canvas.create_text(200, 80, text="🎬 Video file",
                                      fill=FG2, font=("Segoe UI", 16))
        else:
            self._canvas.create_text(200, 80, text=f"{entry.file_type} file",
                                      fill=FG2, font=("Segoe UI", 16))

        # Info
        lines = [
            f"Path:      {entry.path}",
            f"Type:      {entry.file_type}  ({entry.mime_ext})",
            f"Size:      {_human(entry.size_bytes)}",
            f"Date:      {entry.date or '—'}",
        ]
        if entry.width:
            lines.append(f"Dims:      {entry.width} × {entry.height}")
        if entry.camera:
            lines.append(f"Camera:    {entry.camera}")
        if entry.gps:
            lines.append(f"GPS:       {entry.gps[0]:.5f}, {entry.gps[1]:.5f}")
        if entry.quality_grade:
            lines.append(f"Quality:   {entry.quality_grade}  "
                         f"blur={entry.quality_blur:.0f}  "
                         f"exp={entry.quality_exposure:.2f}")
        if not entry.health_ok:
            lines.append(f"Issues:    {'; '.join(entry.health_issues)}")

        self._preview_info.configure(state="normal")
        self._preview_info.delete("1.0", "end")
        self._preview_info.insert("1.0", "\n".join(lines))
        self._preview_info.configure(state="disabled")

        self._desc_var.set(entry.ai_description or "")
        self._proposed_var.set(entry.proposed_name or "")

        self._ocr_text.configure(state="normal")
        self._ocr_text.delete("1.0", "end")
        self._ocr_text.insert("1.0", entry.ocr_text or "")
        self._ocr_text.configure(state="disabled")

        self._transcript_text.configure(state="normal")
        self._transcript_text.delete("1.0", "end")
        self._transcript_text.insert("1.0", entry.transcript or "")
        self._transcript_text.configure(state="disabled")

    def _on_double_click(self, _event=None):
        self._open_lightbox()

    def _open_lightbox(self):
        if not self._selected_entry:
            return
        try:
            from .lightbox import Lightbox
            Lightbox(self, self._entries, self._selected_entry)
        except Exception as e:
            messagebox.showerror("Lightbox", str(e))

    def _rotate_current(self):
        if not self._selected_entry:
            return
        e = self._selected_entry
        if e.file_type != "image":
            return
        try:
            from . import converter
            converter.fix_rotation(e.path)
            self._show_preview(e)
            self._set_status("Rotated")
        except Exception as ex:
            messagebox.showerror("Rotate", str(ex))

    def _open_rename_preview(self):
        if not self._entries:
            messagebox.showinfo("Renames", "No files scanned yet.")
            return
        RenamePreview(self, self._entries)

    def _regroup_events(self):
        try:
            gap = int(self._gap_var.get())
        except ValueError:
            gap = 60
        from . import events
        self._event_groups = events.group_by_events(self._entries, gap_minutes=gap)
        self._populate_events(self._event_groups)

    def _organise_by_event(self):
        if not self._event_groups:
            return
        output = Path(self._output_var.get())
        from . import organizer
        for g in self._event_groups:
            moves = organizer.plan_moves(g.entries, output, mode="event",
                                          event_name=g.display_name)
            if self._apply_var.get():
                log = output / "move_log.json"
                organizer.apply_moves(moves, log_path=log)
        self._set_status("Events organised" if self._apply_var.get()
                         else "Dry-run complete (enable Apply in Export tab)")

    def _organise(self):
        if not self._entries:
            messagebox.showinfo("Organise", "Nothing scanned yet.")
            return
        output = Path(self._output_var.get())
        mode = self._mode_var.get()
        from . import organizer
        moves = organizer.plan_moves(self._entries, output, mode=mode)
        if not self._apply_var.get():
            msg = f"{len(moves)} moves planned ({mode} mode).\nEnable Apply in Export tab to execute."
            messagebox.showinfo("Dry Run", msg)
        else:
            log = output / "move_log.json"
            records = organizer.apply_moves(moves, log_path=log)
            ok = sum(1 for r in records if r["ok"])
            messagebox.showinfo("Done", f"Moved {ok}/{len(records)} files.")

    # ── Tool handlers ─────────────────────────────────────────────────────────

    def _run_in_thread(self, fn, *args, status="Working…"):
        self._set_status(status)
        def _work():
            try:
                msg = fn(*args)
            except ImportError as e:
                msg = str(e)
            except Exception as e:
                msg = f"Error: {e}"
            self.after(0, lambda: self._set_status(msg or "Done"))
        threading.Thread(target=_work, daemon=True).start()

    def _tool_heic_convert(self):
        if not self._scan_folder:
            return
        def _fn():
            from . import converter
            converted = converter.batch_convert_heic(self._scan_folder)
            return f"Converted {len(converted)} HEIC files"
        self._run_in_thread(_fn, status="Converting HEIC…")

    def _tool_fix_rotation(self):
        def _fn():
            from . import converter
            n = sum(1 for e in self._entries if e.file_type == "image"
                    and _try(lambda: converter.fix_rotation(e.path)))
            return f"Fixed rotation on {n} images"
        self._run_in_thread(_fn, status="Fixing rotation…")

    def _tool_strip_gps(self):
        def _fn():
            from . import converter
            n = sum(1 for e in self._entries if e.file_type == "image"
                    and _try(lambda: converter.strip_metadata(e.path, strip_gps_only=True)))
            return f"Stripped GPS from {n} images"
        self._run_in_thread(_fn, status="Stripping GPS…")

    def _tool_strip_all(self):
        if not messagebox.askyesno("Strip Metadata",
                                    "Remove ALL EXIF metadata from all images? This is irreversible."):
            return
        def _fn():
            from . import converter
            n = sum(1 for e in self._entries if e.file_type == "image"
                    and _try(lambda: converter.strip_metadata(e.path)))
            return f"Stripped metadata from {n} images"
        self._run_in_thread(_fn, status="Stripping metadata…")

    def _tool_auto_enhance(self):
        def _fn():
            from . import converter
            n = sum(1 for e in self._entries if e.file_type == "image"
                    and _try(lambda: converter.auto_enhance(e.path)))
            return f"Enhanced {n} images"
        self._run_in_thread(_fn, status="Enhancing images…")

    def _tool_blur_faces(self):
        def _fn():
            from . import faces as f_mod
            n = sum(1 for e in self._entries if e.file_type == "image"
                    and _try(lambda: f_mod.blur_faces(e.path)))
            return f"Blurred faces in {n} images"
        self._run_in_thread(_fn, status="Blurring faces…")

    def _tool_remove_bg(self):
        def _fn():
            from . import converter
            n = 0
            for e in self._entries:
                if e.file_type == "image":
                    try:
                        out = e.path.with_suffix(".nobg.png")
                        converter.remove_background(e.path, out)
                        n += 1
                    except ImportError as ie:
                        return str(ie)
                    except Exception:
                        pass
            return f"Removed background from {n} images"
        self._run_in_thread(_fn, status="Removing backgrounds…")

    def _tool_run_ocr(self):
        def _fn():
            from . import ocr
            if not ocr.is_available():
                return ("Tesseract not found. Download from "
                        "https://tesseract-ocr.github.io/ and add to PATH.")
            ocr.extract_all(self._entries)
            n = sum(1 for e in self._entries if e.ocr_text)
            return f"OCR complete: {n} files with text"
        self._run_in_thread(_fn, status="Running OCR…")

    def _tool_batch_convert(self):
        src = self._src_ext_var.get()
        dst = self._dst_ext_var.get()
        if not self._scan_folder:
            return
        def _fn():
            from . import converter
            files = converter.batch_convert_format(self._scan_folder, src, dst)
            return f"Converted {len(files)} {src.upper()} → {dst.upper()}"
        self._run_in_thread(_fn, status=f"Converting {src}→{dst}…")

    def _tool_batch_resize(self):
        try:
            max_px = int(self._max_px_var.get())
        except ValueError:
            messagebox.showerror("Resize", "Invalid max pixels value")
            return
        if not self._scan_folder:
            return
        def _fn():
            from . import converter
            files = converter.batch_resize(self._scan_folder, max_dimension=max_px)
            return f"Resized {len(files)} images to max {max_px}px"
        self._run_in_thread(_fn, status="Resizing images…")

    def _tool_score_quality(self):
        def _fn():
            from . import quality as qmod
            qmod.score_all(self._entries)
            self.after(0, lambda: self._populate_tree(self._entries))
            grades = {g: sum(1 for e in self._entries if e.quality_grade == g)
                      for g in ("A", "B", "C", "D", "F")}
            return "Quality: " + "  ".join(f"{g}:{n}" for g, n in grades.items() if n)
        self._run_in_thread(_fn, status="Scoring quality…")

    def _tool_detect_faces(self):
        def _fn():
            from . import faces as f_mod
            for e in self._entries:
                f_mod.update_entry_face_count(e)
            self.after(0, lambda: self._populate_tree(self._entries))
            total = sum(e.face_count or 0 for e in self._entries)
            return f"Detected {total} faces across {len(self._entries)} files"
        self._run_in_thread(_fn, status="Detecting faces…")

    def _tool_watermark(self):
        text = self._wm_text_var.get().strip()
        if not text:
            messagebox.showinfo("Watermark", "Enter watermark text first.")
            return
        def _fn():
            from . import watermark as wm
            sel = self._get_selected_entries()
            targets = sel if sel else [e for e in self._entries if e.file_type == "image"]
            results = wm.batch_watermark(targets, text=text)
            return f"Watermarked {len(results)} images"
        self._run_in_thread(_fn, status="Watermarking…")

    def _get_selected_entries(self):
        sel = self._tree.selection()
        return [self._entry_map[iid] for iid in sel if iid in self._entry_map]

    def _tool_compress_video(self):
        e = self._selected_entry
        if not e or e.file_type != "video":
            messagebox.showinfo("Compress", "Select a video file first.")
            return
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.compress_video(e.path)
            return f"Compressed → {out.name}"
        self._run_in_thread(_fn, status="Compressing video…")

    def _tool_convert_mp4(self):
        e = self._selected_entry
        if not e or e.file_type != "video":
            messagebox.showinfo("Convert", "Select a video file first.")
            return
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.convert_to_mp4(e.path)
            return f"Converted → {out.name}"
        self._run_in_thread(_fn, status="Converting to MP4…")

    def _tool_trim_video(self):
        e = self._selected_entry
        if not e or e.file_type != "video":
            messagebox.showinfo("Trim", "Select a video file first.")
            return
        try:
            start = float(self._trim_start_var.get())
            end   = float(self._trim_end_var.get())
        except ValueError:
            messagebox.showerror("Trim", "Invalid start/end values")
            return
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.trim_video(e.path, start, end)
            return f"Trimmed → {out.name}"
        self._run_in_thread(_fn, status="Trimming video…")

    def _tool_extract_audio(self):
        e = self._selected_entry
        if not e or e.file_type not in ("video", "audio"):
            messagebox.showinfo("Extract Audio", "Select a video/audio file first.")
            return
        fmt = self._audio_fmt_var.get()
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.extract_audio(e.path, fmt=fmt)
            return f"Audio → {out.name}"
        self._run_in_thread(_fn, status="Extracting audio…")

    def _tool_video_gif(self):
        e = self._selected_entry
        if not e or e.file_type != "video":
            messagebox.showinfo("GIF", "Select a video file first.")
            return
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.video_to_gif(e.path)
            return f"GIF → {out.name}"
        self._run_in_thread(_fn, status="Making GIF…")

    def _tool_video_sheet(self):
        e = self._selected_entry
        if not e or e.file_type != "video":
            messagebox.showinfo("Sheet", "Select a video file first.")
            return
        def _fn():
            from . import ffmpeg_tools as ff
            out = ff.make_video_sheet(e.path)
            return f"Sheet → {out.name}"
        self._run_in_thread(_fn, status="Making video sheet…")

    def _tool_merge_videos(self):
        sel = self._get_selected_entries()
        vids = [e for e in sel if e.file_type == "video"]
        if len(vids) < 2:
            messagebox.showinfo("Merge", "Select 2+ video files in the list first.")
            return
        out_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4"), ("All", "*.*")],
            title="Save merged video as…",
        )
        if not out_path:
            return
        def _fn():
            from . import ffmpeg_tools as ff
            ff.merge_videos([e.path for e in vids], Path(out_path))
            return f"Merged {len(vids)} videos → {Path(out_path).name}"
        self._run_in_thread(_fn, status="Merging videos…")

    def _tool_transcribe(self):
        def _fn():
            from . import transcript as tr
            if not tr.is_available():
                return "Whisper not installed. Run: pip install openai-whisper"
            model = self._whisper_model_var.get()
            tr.transcribe_all(self._entries, model_name=model)
            n = sum(1 for e in self._entries if e.transcript)
            return f"Transcribed {n} files"
        self._run_in_thread(_fn, status="Transcribing videos…")

    def _tool_app_sort(self):
        output = Path(self._output_var.get())
        def _fn():
            from . import organizer
            moves = organizer.sort_by_app_source(
                self._entries, output, apply=self._apply_var.get())
            return (f"Sorted {len(moves)} files by app source"
                    + ("" if self._apply_var.get() else " (dry-run)"))
        self._run_in_thread(_fn, status="Sorting by app source…")

    def _tool_fix_timestamps(self):
        def _fn():
            from . import repair
            n = repair.fix_all_timestamps(self._entries)
            return f"Fixed timestamps on {n} files"
        self._run_in_thread(_fn, status="Fixing timestamps…")

    def _tool_find_corrupt(self):
        def _fn():
            from . import repair
            corrupt = repair.scan_corrupt(self._entries)
            self.after(0, lambda: self._populate_tree(self._entries))
            return f"Found {len(corrupt)} corrupted files (highlighted)"
        self._run_in_thread(_fn, status="Scanning for corrupted files…")

    def _tool_find_stale(self):
        def _fn():
            from . import repair
            stale = repair.find_stale(self._entries)
            return (f"Found {len(stale)} stale files (no EXIF, old mtime). "
                    "Use filter to search by date.")
        self._run_in_thread(_fn, status="Finding stale files…")

    def _tool_undo(self):
        output = Path(self._output_var.get())
        log = output / "move_log.json"
        if not log.exists():
            messagebox.showinfo("Undo", "No move log found.")
            return
        if not messagebox.askyesno("Undo", "Reverse the last organise run?"):
            return
        def _fn():
            from . import organizer
            records = organizer.undo_last_run(log)
            ok = sum(1 for r in records if r["ok"])
            return f"Undone: {ok}/{len(records)} moves reversed"
        self._run_in_thread(_fn, status="Undoing last run…")

    def _tool_secure_delete(self):
        sel = self._get_selected_entries()
        if not sel:
            messagebox.showinfo("Secure Delete", "Select files in the list first.")
            return
        if not messagebox.askyesno("Secure Delete",
                                    f"Securely overwrite and delete {len(sel)} file(s)? "
                                    "This CANNOT be undone."):
            return
        def _fn():
            from . import repair
            n = sum(1 for e in sel if repair.secure_delete(e.path))
            self._entries = [e for e in self._entries if e not in sel]
            self.after(0, lambda: self._populate_tree(self._entries))
            return f"Securely deleted {n} files"
        self._run_in_thread(_fn, status="Secure deleting…")

    # ── Toggle watch ──────────────────────────────────────────────────────────

    def _toggle_watch(self):
        if self._watcher and self._watcher.is_running:
            self._watcher.stop()
            self._watcher = None
            self._watch_btn.configure(bg=BG2, text="👁 Watch")
            self._set_status("Watch mode off")
            return
        if not self._scan_folder:
            self._browse()
            if not self._scan_folder:
                return
        try:
            from .watcher import FolderWatcher
            self._watcher = FolderWatcher(self._scan_folder, self._on_new_file)
            self._watcher.start()
            self._watch_btn.configure(bg=GREEN, text="● Watching")
            self._set_status(f"Watching {self._scan_folder}")
        except ImportError:
            messagebox.showinfo("Watch Mode",
                                "watchdog not installed. Run: pip install watchdog")

    def _on_new_file(self, path: Path):
        from . import scanner, health, quality as qmod
        entry = scanner.scan(path.parent, recursive=False)
        matching = [e for e in entry if e.path == path]
        if not matching:
            return
        e = matching[0]
        health.check(e)
        qmod.score_entry(e)
        self._entries.append(e)
        self.after(0, lambda: self._populate_tree(self._entries))
        self.after(0, lambda: self._set_status(f"New file: {path.name}"))

    # ── Export handlers ───────────────────────────────────────────────────────

    def _export_json(self):
        out = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="manifest.json",
        )
        if out:
            from . import exporter
            exporter.export_json(self._entries, Path(out))
            self._set_status(f"JSON saved → {Path(out).name}")

    def _export_csv(self):
        out = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="media.csv",
        )
        if out:
            from . import exporter
            exporter.export_csv(self._entries, Path(out))
            self._set_status(f"CSV saved → {Path(out).name}")

    def _export_html(self):
        out = filedialog.askdirectory(title="Save HTML gallery to folder…")
        if out:
            from . import exporter
            result = exporter.export_html(self._entries, Path(out))
            self._set_status(f"HTML gallery → {result}")

    def _export_map(self):
        out = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML", "*.html")],
            initialfile="gps_map.html",
        )
        if out:
            from . import mapview
            mapview.export_map(self._entries, Path(out))
            self._set_status(f"Map saved → {Path(out).name}")

    def _export_contact_sheet(self):
        out = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg")],
            initialfile="contact_sheet.jpg",
        )
        if not out:
            return
        def _fn():
            from . import contact_sheet as cs
            cs.make_contact_sheet(self._entries, Path(out),
                                   title=str(self._scan_folder or ""))
            return f"Contact sheet → {Path(out).name}"
        self._run_in_thread(_fn, status="Building contact sheet…")

    def _export_calendar(self):
        out = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML", "*.html")],
            initialfile="calendar_heatmap.html",
        )
        if not out:
            return
        self._set_status("Generating calendar heat map…")
        from collections import Counter
        counts = Counter(
            e.date.strftime("%Y-%m-%d") for e in self._entries if e.date
        )
        if not counts:
            messagebox.showinfo("Calendar", "No dated files found.")
            return
        min_c, max_c = min(counts.values()), max(counts.values())
        cells = []
        for date_str in sorted(counts):
            v = counts[date_str]
            intensity = int(50 + 180 * (v - min_c) / max(max_c - min_c, 1))
            color = f"rgb({intensity},{30},{80})"
            cells.append(
                f'<div class="day" style="background:{color}" '
                f'title="{date_str}: {v} files">{date_str[-2:]}</div>'
            )
        html = (
            "<html><head><title>Calendar Heat Map</title>"
            "<style>body{background:#1a1a2e;color:#e0e0e0;font-family:sans-serif}"
            ".grid{display:flex;flex-wrap:wrap;gap:4px;padding:16px}"
            ".day{width:32px;height:32px;display:flex;align-items:center;"
            "justify-content:center;border-radius:4px;font-size:10px;"
            "cursor:default;color:#fff}</style></head><body>"
            f"<h2 style='color:#e94560;padding:16px'>📅 Activity Calendar "
            f"({len(counts)} days)</h2><div class='grid'>"
            + "".join(cells) + "</div></body></html>"
        )
        Path(out).write_text(html, encoding="utf-8")
        self._set_status(f"Calendar → {Path(out).name}")


# ── Lightbox window ───────────────────────────────────────────────────────────

class Lightbox(tk.Toplevel):
    def __init__(self, master, entries, current):
        super().__init__(master)
        self.title("Lightbox")
        self.configure(bg=BG)
        self.geometry("900x650")
        self._entries = [e for e in entries if e.file_type in ("image", "video")]
        self._idx = next(
            (i for i, e in enumerate(self._entries) if e is current), 0
        )
        self._zoom = 1.0
        self._pan_x = self._pan_y = 0
        self._drag_start = None
        self._build()
        self._load()
        self.bind("<Left>",   lambda _: self._nav(-1))
        self.bind("<Right>",  lambda _: self._nav(1))
        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<d>",      lambda _: self._mark_delete())
        self.bind("<k>",      lambda _: self._mark_keep())
        self.bind("<r>",      lambda _: self._rotate())

    def _build(self):
        self._canvas = tk.Canvas(self, bg=BG3, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<ButtonPress-1>",   self._on_drag_start)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", lambda _: setattr(self, "_drag_start", None))

        ctrl = tk.Frame(self, bg=BG2)
        ctrl.pack(fill="x")
        for txt, cmd in [("← Prev", lambda: self._nav(-1)),
                          ("Next →", lambda: self._nav(1)),
                          ("⟳ Rotate", self._rotate),
                          ("🗑 Mark Delete", self._mark_delete),
                          ("✓ Keep", self._mark_keep)]:
            tk.Button(ctrl, text=txt, bg=BG3, fg=FG, relief="flat",
                      command=cmd, padx=8).pack(side="left", padx=4, pady=4)
        self._overlay = tk.Label(ctrl, text="", bg=BG2, fg=FG2,
                                  font=("Segoe UI", 9))
        self._overlay.pack(side="right", padx=12)

    def _load(self):
        self._canvas.delete("all")
        if not self._entries:
            return
        e = self._entries[self._idx]
        cw = self._canvas.winfo_width() or 860
        ch = self._canvas.winfo_height() or 580

        if e.file_type == "image":
            try:
                from PIL import Image, ImageTk
                img = Image.open(e.path).convert("RGB")
                # Apply zoom
                nw = int(img.width * self._zoom)
                nh = int(img.height * self._zoom)
                img = img.resize((nw, nh), Image.LANCZOS)
                self._photo = ImageTk.PhotoImage(img)
                cx = cw // 2 + self._pan_x
                cy = ch // 2 + self._pan_y
                self._canvas.create_image(cx, cy, image=self._photo, anchor="center")
            except Exception as ex:
                self._canvas.create_text(cw // 2, ch // 2,
                                          text=f"Preview error: {ex}", fill=FG2)
        else:
            self._canvas.create_text(cw // 2, ch // 2,
                                      text=f"🎬 {e.path.name}", fill=FG2,
                                      font=("Segoe UI", 16))

        grade = f" [{e.quality_grade}]" if e.quality_grade else ""
        date_str = e.date.strftime("%Y-%m-%d") if e.date else ""
        self._overlay.configure(
            text=f"{self._idx+1}/{len(self._entries)}  {e.path.name}  "
                 f"{date_str}{grade}  zoom:{self._zoom:.1f}x")

    def _nav(self, delta: int):
        self._idx = (self._idx + delta) % len(self._entries)
        self._zoom = 1.0
        self._pan_x = self._pan_y = 0
        self._load()

    def _on_wheel(self, event):
        factor = 1.1 if event.delta > 0 else 0.9
        self._zoom = max(0.2, min(self._zoom * factor, 8.0))
        self._load()

    def _on_drag_start(self, event):
        self._drag_start = (event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._pan_x += dx
            self._pan_y += dy
            self._drag_start = (event.x, event.y)
            self._load()

    def _mark_delete(self):
        e = self._entries[self._idx]
        e.metadata["marked_delete"] = True
        self._overlay.configure(fg=RED)
        self._nav(1)

    def _mark_keep(self):
        e = self._entries[self._idx]
        e.metadata.pop("marked_delete", None)
        self._overlay.configure(fg=GREEN)

    def _rotate(self):
        e = self._entries[self._idx]
        if e.file_type != "image":
            return
        try:
            from . import converter
            converter.fix_rotation(e.path)
        except Exception:
            pass
        self._load()


# ── Rename preview window ──────────────────────────────────────────────────────

class RenamePreview(tk.Toplevel):
    def __init__(self, master, entries):
        super().__init__(master)
        self.title("Review AI Renames")
        self.configure(bg=BG)
        self.geometry("800x500")
        self._entries = [e for e in entries
                         if e.proposed_name and e.proposed_name != e.path.name]

        cols = ("orig", "proposed", "category", "apply")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   selectmode="extended")
        self._tree.heading("orig",     text="Original Name")
        self._tree.heading("proposed", text="Proposed Name")
        self._tree.heading("category", text="Category")
        self._tree.heading("apply",    text="Apply?")
        self._tree.column("orig",     width=200)
        self._tree.column("proposed", width=220)
        self._tree.column("category", width=100)
        self._tree.column("apply",    width=50, anchor="center")

        for e in self._entries:
            self._tree.insert("", "end", iid=str(id(e)),
                               values=(e.path.name, e.proposed_name,
                                       e.ai_category or "", "✓"))

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", pady=8)

        btns = tk.Frame(self, bg=BG)
        btns.pack(fill="x", padx=8, pady=8)
        tk.Button(btns, text="Apply All", bg=ACCENT, fg="white",
                  relief="flat", font=("Segoe UI", 10, "bold"),
                  command=self._apply_all).pack(side="left", padx=4)
        tk.Button(btns, text="Apply Selected", bg=BG2, fg=FG,
                  relief="flat", command=self._apply_selected).pack(side="left", padx=4)
        tk.Button(btns, text="Skip All", bg=BG2, fg=FG2,
                  relief="flat", command=self.destroy).pack(side="left", padx=4)
        self._status = tk.Label(btns, text="", bg=BG, fg=FG2)
        self._status.pack(side="right")

    def _do_rename(self, iids):
        entry_map = {str(id(e)): e for e in self._entries}
        done = 0
        for iid in iids:
            e = entry_map.get(iid)
            if not e:
                continue
            dest = e.path.parent / e.proposed_name
            if dest == e.path:
                continue
            # Avoid collision
            i = 1
            while dest.exists():
                dest = e.path.parent / f"{dest.stem}_{i}{dest.suffix}"
                i += 1
            try:
                e.path.rename(dest)
                e.path = dest
                done += 1
            except Exception:
                pass
        self._status.configure(text=f"Renamed {done} files")

    def _apply_all(self):
        self._do_rename([str(id(e)) for e in self._entries])

    def _apply_selected(self):
        self._do_rename(list(self._tree.selection()))


# ── Utility ────────────────────────────────────────────────────────────────────

def _try(fn) -> bool:
    try:
        fn()
        return True
    except Exception:
        return False


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
