"""Sleek dark-theme GUI for Media Organizer."""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# -- Colour palette -------------------------------------------------------
BG      = '#1a1a2e'
CARD    = '#16213e'
CARD2   = '#0f3460'
ACCENT  = '#e94560'
TEXT    = '#eaeaea'
MUTED   = '#888888'
GREEN   = '#4caf50'
RED     = '#f44336'
YELLOW  = '#ff9800'
PURPLE  = '#ce93d8'

FONT_TITLE  = ('Segoe UI', 15, 'bold')
FONT_HEAD   = ('Segoe UI', 11, 'bold')
FONT_BODY   = ('Segoe UI', 10)
FONT_SMALL  = ('Segoe UI', 9)
FONT_MONO   = ('Consolas', 9)

FILE_ICONS = {'image': '\U0001f5bc', 'video': '\U0001f4f9', 'pdf': '\U0001f4c4',
               'document': '\U0001f4cb', 'unknown': '\U0001f4c1'}
STATUS_ICON = {'ok': '✓', 'corrupt': '✕', 'duplicate': '⚠',
               'threat': '☠', 'pending': '·'}


def _human(b: float) -> str:
    for u in ('B', 'KB', 'MB', 'GB'):
        if b < 1024:
            return f'{b:.1f} {u}'
        b /= 1024
    return f'{b:.1f} TB'


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title('Media Organizer')
        self.geometry('1150x740')
        self.minsize(820, 560)
        self.configure(bg=BG)

        self._entries: list = []
        self._dup_groups: dict = {}
        self._report: dict = {}
        self._av_report: dict = {}
        self._selected = None
        self._cancel = threading.Event()
        self._q: queue.Queue = queue.Queue()

        self._styles()
        self._build()
        self._poll()
        self.after(600, self._ping_ollama)
        self.after(800, self._ping_av)

    # -- Styles -----------------------------------------------------------

    def _styles(self) -> None:
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=TEXT, font=FONT_BODY)
        s.configure('TFrame', background=BG)
        s.configure('Card.TFrame', background=CARD)
        s.configure('TLabel', background=BG, foreground=TEXT)
        s.configure('Card.TLabel', background=CARD, foreground=TEXT)
        s.configure('Muted.TLabel', foreground=MUTED, font=FONT_SMALL)
        s.configure('Accent.TLabel', foreground=ACCENT)
        s.configure('Accent.TButton', background=ACCENT, foreground='white',
                     font=('Segoe UI', 10, 'bold'), borderwidth=0, padding=(12, 6))
        s.map('Accent.TButton', background=[('active', '#c73652'), ('disabled', '#444')])
        s.configure('Danger.TButton', background=RED, foreground='white',
                     font=('Segoe UI', 10, 'bold'), borderwidth=0, padding=(12, 6))
        s.map('Danger.TButton', background=[('active', '#c62828'), ('disabled', '#444')])
        s.configure('Flat.TButton', background=CARD, foreground=TEXT,
                     borderwidth=1, relief='flat', padding=(8, 5))
        s.map('Flat.TButton', background=[('active', CARD2)])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=CARD, foreground=MUTED,
                     padding=(14, 7), borderwidth=0)
        s.map('TNotebook.Tab', background=[('selected', CARD2)], foreground=[('selected', TEXT)])
        s.configure('Treeview', background=CARD, foreground=TEXT,
                     fieldbackground=CARD, rowheight=30, borderwidth=0, font=FONT_SMALL)
        s.configure('Treeview.Heading', background=CARD2, foreground=ACCENT,
                     relief='flat', font=('Segoe UI', 9, 'bold'))
        s.map('Treeview', background=[('selected', CARD2)], foreground=[('selected', TEXT)])
        s.configure('TProgressbar', background=ACCENT, troughcolor=CARD,
                     borderwidth=0, thickness=5)
        s.configure('TCheckbutton', background=BG, foreground=TEXT, focusthickness=0)
        s.map('TCheckbutton', background=[('active', BG)])
        s.configure('TCombobox', fieldbackground=CARD, background=CARD,
                     foreground=TEXT, selectbackground=ACCENT)
        s.map('TCombobox', fieldbackground=[('readonly', CARD)])
        s.configure('TScrollbar', background=CARD, troughcolor=BG, borderwidth=0)

    # -- Layout -----------------------------------------------------------

    def _build(self) -> None:
        self._header()
        self._toolbar()
        self._main_area()
        self._statusbar()

    def _header(self) -> None:
        h = tk.Frame(self, bg=CARD, height=52)
        h.pack(fill='x')
        h.pack_propagate(False)
        tk.Label(h, text='  \U0001f5c2  Media Organizer', bg=CARD, fg=ACCENT,
                 font=FONT_TITLE).pack(side='left', padx=10)
        tk.Label(h, text='v1.2', bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left')
        self._av_lbl = tk.Label(h, text='  ☠  AV: checking…  ',
                                bg=CARD2, fg=MUTED, font=FONT_SMALL, padx=8, pady=4)
        self._av_lbl.pack(side='right', padx=4)
        self._ollama_lbl = tk.Label(h, text='  ●  Ollama: checking…  ',
                                    bg=CARD2, fg=MUTED, font=FONT_SMALL, padx=8, pady=4)
        self._ollama_lbl.pack(side='right', padx=12)

    def _toolbar(self) -> None:
        bar = tk.Frame(self, bg=CARD2, pady=7)
        bar.pack(fill='x')
        tk.Label(bar, text='  Folder:', bg=CARD2, fg=TEXT, font=FONT_BODY).pack(side='left')
        self._folder_var = tk.StringVar(value='Select a folder…')
        tk.Entry(bar, textvariable=self._folder_var, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=FONT_MONO, width=32,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=CARD).pack(side='left', padx=(4, 3), ipady=4)
        ttk.Button(bar, text='Browse', style='Flat.TButton',
                   command=self._browse).pack(side='left', padx=(0, 10))
        tk.Frame(bar, bg=MUTED, width=1).pack(side='left', fill='y', pady=3)
        tk.Label(bar, text='  Mode:', bg=CARD2, fg=TEXT, font=FONT_BODY).pack(side='left', padx=(8, 4))
        self._mode = tk.StringVar(value='type')
        ttk.Combobox(bar, textvariable=self._mode, values=['type', 'date', 'content'],
                     state='readonly', width=9).pack(side='left', padx=(0, 10))
        tk.Label(bar, text='Output:', bg=CARD2, fg=TEXT, font=FONT_BODY).pack(side='left', padx=(0, 4))
        self._output_var = tk.StringVar(value='./Organized')
        tk.Entry(bar, textvariable=self._output_var, bg=CARD, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=FONT_MONO, width=16,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=CARD).pack(side='left', padx=(0, 6), ipady=4)
        self._recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text='Recursive', variable=self._recursive_var).pack(side='left', padx=6)
        self._scan_btn = ttk.Button(bar, text='⟳  Scan & Analyze',
                                    style='Accent.TButton', command=self._start_scan)
        self._scan_btn.pack(side='right', padx=4)
        self._av_btn = ttk.Button(bar, text='☠  Virus Scan',
                                  style='Danger.TButton', command=self._start_av_scan,
                                  state='disabled')
        self._av_btn.pack(side='right', padx=4)
        self._apply_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='Apply moves', variable=self._apply_var).pack(side='right', padx=(12, 4))

    def _main_area(self) -> None:
        pw = tk.PanedWindow(self, orient='horizontal', bg=BG, sashwidth=6, sashrelief='flat')
        pw.pack(fill='both', expand=True, padx=8, pady=(8, 4))
        left = tk.Frame(pw, bg=BG)
        pw.add(left, minsize=230, width=330)
        tk.Label(left, text='FILES', bg=BG, fg=MUTED,
                 font=('Segoe UI', 8, 'bold')).pack(anchor='w', padx=4, pady=(0, 3))
        cols = ('ico', 'name', 'size', 'st')
        self._tree = ttk.Treeview(left, columns=cols, show='headings', selectmode='browse')
        self._tree.heading('ico', text='')
        self._tree.heading('name', text='Name')
        self._tree.heading('size', text='Size')
        self._tree.heading('st', text='')
        self._tree.column('ico', width=28, stretch=False, anchor='center')
        self._tree.column('name', width=195, anchor='w')
        self._tree.column('size', width=62, anchor='e')
        self._tree.column('st', width=22, stretch=False, anchor='center')
        self._tree.tag_configure('ok', foreground=TEXT)
        self._tree.tag_configure('bad', foreground=RED)
        self._tree.tag_configure('dup', foreground=YELLOW)
        self._tree.tag_configure('threat', foreground=PURPLE)
        self._tree.tag_configure('pend', foreground=MUTED)
        vsb = ttk.Scrollbar(left, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        self._tree.bind('<<TreeviewSelect>>', self._on_select)
        right = tk.Frame(pw, bg=BG)
        pw.add(right, minsize=420)
        self._nb = ttk.Notebook(right)
        self._nb.pack(fill='both', expand=True)
        self._tab_preview()
        self._tab_duplicates()
        self._tab_threats()
        self._tab_storage()
        self._tab_export()
        self._tab_tools()

    def _tab_preview(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  \U0001f5bc  Preview  ')
        th = tk.Frame(f, bg=CARD, height=210)
        th.pack(fill='x', padx=6, pady=(6, 0))
        th.pack_propagate(False)
        self._thumb = tk.Label(th, bg=CARD, compound='center')
        self._thumb.place(relwidth=1, relheight=1)
        self._thumb_hint = tk.Label(th, bg=CARD, fg=MUTED, font=FONT_SMALL,
                                    text='Select a file to preview')
        self._thumb_hint.place(relx=.5, rely=.5, anchor='center')
        info = tk.Frame(f, bg=CARD, padx=12, pady=8)
        info.pack(fill='x', padx=6, pady=4)
        self._info_name = tk.Label(info, bg=CARD, fg=TEXT, font=FONT_HEAD,
                                   anchor='w', wraplength=480, justify='left')
        self._info_name.pack(fill='x')
        self._info_meta = tk.Label(info, bg=CARD, fg=MUTED, font=FONT_SMALL, anchor='w')
        self._info_meta.pack(fill='x')
        self._info_health = tk.Label(info, bg=CARD, fg=GREEN, font=FONT_SMALL, anchor='w')
        self._info_health.pack(fill='x')
        self._info_av = tk.Label(info, bg=CARD, fg=GREEN, font=FONT_SMALL, anchor='w', text='')
        self._info_av.pack(fill='x')
        ai_f = tk.Frame(f, bg=CARD, padx=12, pady=8)
        ai_f.pack(fill='x', padx=6, pady=2)
        tk.Label(ai_f, text='AI Description', bg=CARD, fg=ACCENT,
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self._desc = tk.Text(ai_f, bg=CARD2, fg=TEXT, insertbackground=TEXT,
                             relief='flat', font=FONT_BODY, height=3, wrap='word',
                             padx=6, pady=5, highlightthickness=0)
        self._desc.pack(fill='x', pady=(4, 0))
        nm_f = tk.Frame(f, bg=CARD, padx=12, pady=8)
        nm_f.pack(fill='x', padx=6, pady=2)
        tk.Label(nm_f, text='Proposed Name', bg=CARD, fg=ACCENT,
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self._proposed = tk.StringVar()
        tk.Entry(nm_f, textvariable=self._proposed, bg=CARD2, fg=TEXT,
                 insertbackground=TEXT, relief='flat', font=FONT_MONO,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=CARD2).pack(fill='x', pady=(4, 0), ipady=5)
        bf = tk.Frame(f, bg=BG)
        bf.pack(fill='x', padx=6, pady=(2, 4))
        ttk.Button(bf, text='Save edits', style='Flat.TButton',
                   command=self._save_edit).pack(side='right')

    def _tab_duplicates(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  ⚠  Duplicates  ')
        hdr = tk.Frame(f, bg=CARD, padx=12, pady=8)
        hdr.pack(fill='x')
        self._dup_hdr = tk.Label(hdr, bg=CARD, fg=TEXT, font=FONT_BODY,
                                 text='No duplicates found yet — run a scan first.')
        self._dup_hdr.pack(anchor='w')
        cols = ('grp', 'file', 'size')
        self._dup_tree = ttk.Treeview(f, columns=cols, show='headings')
        self._dup_tree.heading('grp', text='Group')
        self._dup_tree.heading('file', text='File')
        self._dup_tree.heading('size', text='Size')
        self._dup_tree.column('grp', width=100, stretch=False)
        self._dup_tree.column('file', width=300)
        self._dup_tree.column('size', width=80, anchor='e')
        vsb2 = ttk.Scrollbar(f, orient='vertical', command=self._dup_tree.yview)
        self._dup_tree.configure(yscrollcommand=vsb2.set)
        self._dup_tree.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        vsb2.pack(side='right', fill='y', pady=6, padx=(0, 6))

    def _tab_threats(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  ☠  Threats  ')
        hdr = tk.Frame(f, bg=CARD, padx=12, pady=10)
        hdr.pack(fill='x')
        self._threat_hdr = tk.Label(hdr, bg=CARD, fg=TEXT, font=FONT_BODY,
                                    text='Run ☠ Virus Scan (after scanning files) to check for threats.')
        self._threat_hdr.pack(anchor='w')
        self._threat_engine_lbl = tk.Label(hdr, bg=CARD, fg=MUTED, font=FONT_SMALL, text='')
        self._threat_engine_lbl.pack(anchor='w')
        cols = ('file', 'threat')
        self._threat_tree = ttk.Treeview(f, columns=cols, show='headings')
        self._threat_tree.heading('file', text='File')
        self._threat_tree.heading('threat', text='Threat Detected')
        self._threat_tree.column('file', width=260)
        self._threat_tree.column('threat', width=300)
        self._threat_tree.tag_configure('threat', foreground=PURPLE)
        vsb_t = ttk.Scrollbar(f, orient='vertical', command=self._threat_tree.yview)
        self._threat_tree.configure(yscrollcommand=vsb_t.set)
        self._threat_tree.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=6)
        vsb_t.pack(side='right', fill='y', pady=6, padx=(0, 6))

    def _tab_storage(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  \U0001f4ca  Storage  ')
        self._chart = tk.Canvas(f, bg=CARD, height=170, highlightthickness=0)
        self._chart.pack(fill='x', padx=6, pady=6)
        self._storage_txt = tk.Text(f, bg=BG, fg=TEXT, font=FONT_MONO,
                                    relief='flat', state='disabled',
                                    wrap='none', highlightthickness=0)
        vsb3 = ttk.Scrollbar(f, orient='vertical', command=self._storage_txt.yview)
        self._storage_txt.configure(yscrollcommand=vsb3.set)
        self._storage_txt.pack(side='left', fill='both', expand=True, padx=(6, 0), pady=(0, 6))
        vsb3.pack(side='right', fill='y', pady=(0, 6), padx=(0, 6))

    def _tab_export(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  \U0001f4be  Export  ')
        card = tk.Frame(f, bg=CARD, padx=18, pady=16)
        card.pack(fill='x', padx=8, pady=8)
        tk.Label(card, text='Export Results', bg=CARD, fg=ACCENT,
                 font=FONT_HEAD).pack(anchor='w', pady=(0, 12))
        for label, cmd in [
            ('\U0001f4cb  Export JSON Manifest', self._exp_json),
            ('\U0001f4ca  Export CSV Spreadsheet', self._exp_csv),
            ('\U0001f310  Export HTML Gallery', self._exp_html),
        ]:
            ttk.Button(card, text=label, style='Flat.TButton',
                       command=cmd, width=28).pack(anchor='w', pady=5)
        tk.Label(f, bg=BG, fg=MUTED, font=FONT_SMALL,
                 text='Run a scan first to populate export data.').pack(anchor='w', padx=8)

    def _tab_tools(self) -> None:
        f = ttk.Frame(self._nb)
        self._nb.add(f, text='  \U0001f6e0  Tools  ')

        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(f, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win, width=e.width))

        def section(title: str) -> tk.Frame:
            h = tk.Frame(inner, bg=CARD2, padx=10, pady=6)
            h.pack(fill='x', padx=8, pady=(12, 0))
            tk.Label(h, text=title, bg=CARD2, fg=ACCENT, font=FONT_HEAD).pack(anchor='w')
            c = tk.Frame(inner, bg=CARD, padx=14, pady=10)
            c.pack(fill='x', padx=8, pady=(0, 2))
            return c

        # ---- Duplicate Finder -------------------------------------------
        df = section('\U0001f50d  Advanced Duplicate Finder')
        tk.Label(df, bg=CARD, fg=MUTED, font=FONT_SMALL, justify='left',
                 text='Full-featured duplicate finder with visual comparison, SSIM scoring,\n'
                      'animated card browser, and recycle-bin deletion. Opens as a new window.'
                 ).pack(anchor='w', pady=(0, 8))
        ttk.Button(df, text='Open Duplicate Finder', style='Accent.TButton',
                   command=self._tools_open_dupe_finder).pack(anchor='w')

        # ---- Image Tools ------------------------------------------------
        img = section('\U0001f5bc  Image Tools')
        tk.Label(img, bg=CARD, fg=MUTED, font=FONT_SMALL,
                 text='All image tools operate on the folder selected in the toolbar.'
                 ).pack(anchor='w', pady=(0, 8))

        # HEIC row
        row = tk.Frame(img, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='HEIC → JPG', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='Quality:', bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 3))
        self._heic_quality = tk.IntVar(value=92)
        ttk.Spinbox(row, from_=60, to=100, textvariable=self._heic_quality,
                    width=5).pack(side='left', padx=(0, 8))
        ttk.Button(row, text='Convert All HEIC', style='Flat.TButton',
                   command=self._tools_heic_convert).pack(side='left')

        # Rotation row
        row = tk.Frame(img, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='Fix EXIF Rotation', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='Rotates pixels to match EXIF orientation tag, in-place.',
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 12))
        ttk.Button(row, text='Fix Rotation', style='Flat.TButton',
                   command=self._tools_fix_rotation).pack(side='left')

        # GPS row
        row = tk.Frame(img, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='Strip GPS Data', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='Removes GPS location metadata from all images.',
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 12))
        ttk.Button(row, text='Strip GPS', style='Flat.TButton',
                   command=self._tools_strip_gps).pack(side='left')

        # Resize row
        row = tk.Frame(img, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='Batch Resize', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='Max px:', bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 3))
        self._resize_max = tk.IntVar(value=1920)
        ttk.Spinbox(row, from_=480, to=8000, increment=160, textvariable=self._resize_max,
                    width=6).pack(side='left', padx=(0, 8))
        tk.Label(row, text='Quality:', bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 3))
        self._resize_quality = tk.IntVar(value=88)
        ttk.Spinbox(row, from_=60, to=100, textvariable=self._resize_quality,
                    width=5).pack(side='left', padx=(0, 8))
        ttk.Button(row, text='Resize Images', style='Flat.TButton',
                   command=self._tools_batch_resize).pack(side='left')

        # ---- Video Tools ------------------------------------------------
        from . import ffmpeg_tools as ft
        vid = section('\U0001f4f9  Video Tools  (requires ffmpeg)')
        if ft.FFMPEG:
            ff_text = f'ffmpeg: {ft.FFMPEG}'
            ff_color = GREEN
        else:
            ff_text = 'ffmpeg not found — download free at https://ffmpeg.org/'
            ff_color = RED
        tk.Label(vid, text=ff_text, bg=CARD, fg=ff_color, font=FONT_SMALL,
                 wraplength=520, justify='left').pack(anchor='w', pady=(0, 8))

        vid_state = '!disabled' if ft.FFMPEG else 'disabled'

        row = tk.Frame(vid, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='Convert to MP4', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='Converts MOV/AVI/WMV/MKV/etc to H.264 MP4.',
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 12))
        btn = ttk.Button(row, text='Convert All to MP4', style='Flat.TButton',
                         command=self._tools_convert_mp4)
        btn.pack(side='left')
        btn.state([vid_state])

        row = tk.Frame(vid, bg=CARD); row.pack(fill='x', pady=3)
        tk.Label(row, text='Compress Videos', bg=CARD, fg=TEXT, font=FONT_BODY,
                 width=20, anchor='w').pack(side='left')
        tk.Label(row, text='CRF:', bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 3))
        self._crf = tk.IntVar(value=23)
        ttk.Spinbox(row, from_=18, to=32, textvariable=self._crf,
                    width=5).pack(side='left', padx=(0, 6))
        tk.Label(row, text='(lower = better quality, larger file)',
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(side='left', padx=(0, 12))
        btn2 = ttk.Button(row, text='Compress Videos', style='Flat.TButton',
                          command=self._tools_compress_video)
        btn2.pack(side='left')
        btn2.state([vid_state])

    def _statusbar(self) -> None:
        bar = tk.Frame(self, bg=CARD, pady=6)
        bar.pack(fill='x', side='bottom')
        self._status = tk.StringVar(value='Ready — select a folder and press Scan & Analyze.')
        tk.Label(bar, textvariable=self._status, bg=CARD, fg=TEXT,
                 font=FONT_SMALL, anchor='w').pack(side='left', padx=10)
        self._apply_btn = ttk.Button(bar, text='  ✓  Apply All  ',
                                     style='Accent.TButton', command=self._apply_all,
                                     state='disabled')
        self._apply_btn.pack(side='right', padx=(0, 10))
        self._cancel_btn = ttk.Button(bar, text='Cancel', style='Flat.TButton',
                                      command=self._do_cancel, state='disabled')
        self._cancel_btn.pack(side='right', padx=4)
        self._prog = ttk.Progressbar(bar, mode='determinate', length=200)
        self._prog.pack(side='right', padx=10)

    # -- Status pings -----------------------------------------------------

    def _ping_ollama(self) -> None:
        def _check():
            try:
                import requests
                r = requests.get('http://localhost:11434/api/tags', timeout=3)
                if r.status_code != 200:
                    return False, []
                models = [m['name'] for m in r.json().get('models', [])]
                vision = [m for m in models
                          if any(v in m for v in ('moondream', 'llava', 'bakllava'))]
                return True, vision
            except Exception:
                return False, []
        def _done(result):
            ok, models = result
            if ok and models:
                self._ollama_lbl.config(text=f'  ●  Ollama: {models[0]}  ', fg=GREEN)
            elif ok:
                self._ollama_lbl.config(text='  ●  Ollama: no vision model  ', fg=YELLOW)
            else:
                self._ollama_lbl.config(text='  ●  Ollama: offline  ', fg=RED)
        threading.Thread(target=lambda: _done(_check()), daemon=True).start()

    def _ping_av(self) -> None:
        def _check():
            from . import antivirus as av
            return av.available_engine()
        def _done(engine):
            if engine == 'defender':
                self._av_lbl.config(text='  ☠  AV: Defender ready  ', fg=GREEN)
            elif engine == 'clamav':
                self._av_lbl.config(text='  ☠  AV: ClamAV ready  ', fg=GREEN)
            else:
                self._av_lbl.config(text='  ☠  AV: not found  ', fg=MUTED)
        threading.Thread(target=lambda: _done(_check()), daemon=True).start()

    # -- Actions ----------------------------------------------------------

    def _browse(self) -> None:
        d = filedialog.askdirectory(title='Select folder to scan')
        if d:
            self._folder_var.set(d)

    def _do_cancel(self) -> None:
        self._cancel.set()
        self._status.set('Cancelling…')

    def _get_tools_folder(self) -> Optional[Path]:
        folder = self._folder_var.get().strip()
        if not folder or folder.startswith('Select'):
            messagebox.showwarning('No folder', 'Please select a folder in the toolbar first.')
            return None
        p = Path(folder)
        if not p.is_dir():
            messagebox.showerror('Not found', f'Folder not found:\n{p}')
            return None
        return p

    # -- Tool actions -----------------------------------------------------

    def _tools_open_dupe_finder(self) -> None:
        try:
            subprocess.Popen([sys.executable, '-m', 'mediaorganizer.dupe_finder'])
        except Exception as exc:
            messagebox.showerror('Error', f'Could not launch Duplicate Finder:\n{exc}')

    def _tools_heic_convert(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        from . import converter as cv
        if not cv.HEIF_AVAILABLE:
            messagebox.showerror('Missing dependency',
                                 'pillow-heif is not installed.\n'
                                 'Re-run run.bat to install it automatically.')
            return
        quality = self._heic_quality.get()
        def _run():
            self._q.put(('status', 'Converting HEIC files…'))
            try:
                results = cv.batch_heic_to_jpg(
                    folder, quality=quality,
                    progress=lambda i, n, nm: self._q.put(('status', f'HEIC {i+1}/{n}: {nm}')))
                self._q.put(('status', f'HEIC → JPG: {len(results)} file(s) converted.'))
            except Exception as exc:
                self._q.put(('status', f'HEIC error: {exc}'))
        threading.Thread(target=_run, daemon=True).start()

    def _tools_fix_rotation(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        from . import converter as cv
        _EXTS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp'}
        def _run():
            paths = [p for p in folder.rglob('*') if p.suffix.lower() in _EXTS]
            self._q.put(('status', f'Fixing rotation for {len(paths)} images…'))
            ok = 0
            for i, p in enumerate(paths):
                try:
                    cv.fix_exif_rotation(p)
                    ok += 1
                except Exception:
                    pass
                if (i + 1) % 20 == 0:
                    self._q.put(('status', f'Fixing rotation {i+1}/{len(paths)}…'))
            self._q.put(('status', f'Rotation fix complete: {ok}/{len(paths)} images.'))
        threading.Thread(target=_run, daemon=True).start()

    def _tools_strip_gps(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        if not messagebox.askyesno('Strip GPS',
                                   'Remove GPS metadata from all images in the selected folder?\n'
                                   'This modifies files in-place.'):
            return
        from . import converter as cv
        _EXTS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp'}
        def _run():
            paths = [p for p in folder.rglob('*') if p.suffix.lower() in _EXTS]
            self._q.put(('status', f'Stripping GPS from {len(paths)} images…'))
            ok = 0
            for p in paths:
                try:
                    cv.strip_gps(p)
                    ok += 1
                except Exception:
                    pass
            self._q.put(('status', f'GPS strip complete: {ok}/{len(paths)} images.'))
        threading.Thread(target=_run, daemon=True).start()

    def _tools_batch_resize(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        max_px = self._resize_max.get()
        quality = self._resize_quality.get()
        if not messagebox.askyesno('Batch Resize',
                                   f'Resize all images with longest side > {max_px}px to max {max_px}px?\n'
                                   'This modifies files in-place.'):
            return
        from . import converter as cv
        def _run():
            self._q.put(('status', 'Batch resizing images…'))
            try:
                modified = cv.batch_resize(
                    folder, max_dimension=max_px, quality=quality,
                    progress=lambda i, n, nm: self._q.put(('status', f'Resize {i+1}/{n}: {nm}')))
                self._q.put(('status', f'Resize complete: {len(modified)} image(s) resized.'))
            except Exception as exc:
                self._q.put(('status', f'Resize error: {exc}'))
        threading.Thread(target=_run, daemon=True).start()

    def _tools_convert_mp4(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        def _run():
            from . import ffmpeg_tools as ft
            self._q.put(('status', 'Converting videos to MP4…'))
            try:
                results = ft.batch_convert_to_mp4(
                    folder,
                    progress=lambda i, n, nm: self._q.put(('status', f'Converting {i+1}/{n}: {nm}')))
                self._q.put(('status', f'MP4 conversion complete: {len(results)} file(s) converted.'))
            except Exception as exc:
                self._q.put(('status', f'Conversion error: {exc}'))
        threading.Thread(target=_run, daemon=True).start()

    def _tools_compress_video(self) -> None:
        folder = self._get_tools_folder()
        if not folder:
            return
        crf = self._crf.get()
        def _run():
            from . import ffmpeg_tools as ft
            self._q.put(('status', f'Compressing videos (CRF={crf})…'))
            try:
                results = ft.batch_compress_videos(
                    folder, crf=crf,
                    progress=lambda i, n, nm: self._q.put(('status', f'Compressing {i+1}/{n}: {nm}')))
                self._q.put(('status', f'Compression complete: {len(results)} video(s) processed.'))
            except Exception as exc:
                self._q.put(('status', f'Compression error: {exc}'))
        threading.Thread(target=_run, daemon=True).start()

    # -- Scan workers -----------------------------------------------------

    def _start_scan(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder or folder.startswith('Select'):
            messagebox.showwarning('No folder', 'Please select a folder first.')
            return
        p = Path(folder)
        if not p.is_dir():
            messagebox.showerror('Not found', f'Directory not found:\n{p}')
            return
        self._entries.clear()
        self._dup_groups.clear()
        self._tree.delete(*self._tree.get_children())
        self._prog['value'] = 0
        self._cancel.clear()
        self._scan_btn.state(['disabled'])
        self._av_btn.state(['disabled'])
        self._cancel_btn.state(['!disabled'])
        self._apply_btn.state(['disabled'])
        threading.Thread(target=self._worker,
                         args=(p, self._recursive_var.get(), self._mode.get()),
                         daemon=True).start()

    def _start_av_scan(self) -> None:
        if not self._entries:
            messagebox.showinfo('Nothing to scan', 'Run a file scan first.')
            return
        from . import antivirus as av
        engine = av.available_engine()
        if engine == 'none':
            messagebox.showwarning(
                'No AV engine',
                'No antivirus engine found.\n\n'
                'Windows Defender should be present on Windows 10/11.\n'
                'Alternatively install ClamAV: https://www.clamav.net/')
            return
        self._av_btn.state(['disabled'])
        self._cancel_btn.state(['!disabled'])
        self._cancel.clear()
        threading.Thread(target=self._av_worker, args=(engine,), daemon=True).start()

    def _worker(self, path: Path, recursive: bool, mode: str) -> None:
        from . import scanner as sc, health as hl, duplicates as dp, analyzer as az
        from . import reporter as rp

        def send(msg: tuple) -> None:
            self._q.put(msg)

        send(('status', 'Scanning files…'))
        try:
            entries = sc.scan(path, recursive=recursive)
        except Exception as exc:
            send(('err', str(exc)))
            return
        total = len(entries)
        send(('prog', 0, total))
        send(('status', f'Checking health of {total} files…'))
        for i, e in enumerate(entries):
            if self._cancel.is_set():
                send(('status', 'Cancelled.'))
                return
            res = hl.check(e)
            e.health_ok, e.health_issues = res.ok, res.issues
            send(('prog', i + 1, total))
            send(('add', e))
        send(('status', 'Finding duplicates…'))
        dup_groups = dp.find_duplicates(entries)
        ai = az.OllamaAnalyzer()
        if ai.is_available():
            send(('status', f'Analyzing {total} files with Ollama…'))
            for i, e in enumerate(entries):
                if self._cancel.is_set():
                    send(('status', 'Cancelled.'))
                    return
                az.analyze_entries([e], ai, need_category=(mode == 'content'))
                send(('prog', i + 1, total))
                send(('status', f'Analyzing {i + 1}/{total}: {e.path.name}'))
                send(('upd', e))
        else:
            from .analyzer import _heuristic_name
            for e in entries:
                if not e.proposed_name:
                    e.proposed_name = _heuristic_name(e)
        report = rp.generate(entries, dup_groups)
        send(('done', entries, dup_groups, report))

    def _av_worker(self, engine: str) -> None:
        from . import antivirus as av

        def prog(i, n, name):
            self._q.put(('prog', i, n))
            self._q.put(('status', f'☠ Scanning {i + 1}/{n}: {name}'))

        self._q.put(('status', f'☠ Starting virus scan with {engine}…'))
        summary = av.scan_entries(self._entries, engine=engine,
                                  progress_cb=prog, cancel_flag=self._cancel)
        for e in self._entries:
            if not e.metadata.get('av_clean', True):
                self._q.put(('upd', e))
        self._q.put(('av_done', summary))

    # -- Queue handler ----------------------------------------------------

    def _poll(self) -> None:
        try:
            while True:
                self._handle(self._q.get_nowait())
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _handle(self, msg: tuple) -> None:
        k = msg[0]
        if k == 'status':
            self._status.set(msg[1])
        elif k == 'prog':
            self._prog['maximum'] = max(msg[2], 1)
            self._prog['value'] = msg[1]
        elif k == 'add':
            self._entries.append(msg[1])
            self._row_add(msg[1])
        elif k == 'upd':
            self._row_upd(msg[1])
        elif k == 'done':
            self._entries, self._dup_groups, self._report = msg[1], msg[2], msg[3]
            self._refresh_dups()
            self._refresh_storage()
            self._scan_btn.state(['!disabled'])
            self._av_btn.state(['!disabled'])
            self._cancel_btn.state(['disabled'])
            self._apply_btn.state(['!disabled'])
            n, d = len(self._entries), len(self._dup_groups)
            u = sum(1 for e in self._entries if not e.health_ok)
            self._status.set(f'Done — {n} files, {d} duplicate groups, {u} issues. '
                             f'Click ☠ Virus Scan to check for threats.')
            self._ping_ollama()
        elif k == 'av_done':
            summary = msg[1]
            self._av_report = summary
            self._refresh_threats(summary)
            self._av_btn.state(['!disabled'])
            self._cancel_btn.state(['disabled'])
            t = summary['threats']
            eng = summary['engine']
            if t:
                self._status.set(f'☠ Virus scan complete ({eng}) — {t} THREAT(S) FOUND. See Threats tab.')
                self._nb.select(2)
            else:
                self._status.set(f'☠ Virus scan complete ({eng}) — all {summary["scanned"]} files clean.')
        elif k == 'err':
            self._status.set(f'Error: {msg[1]}')
            self._scan_btn.state(['!disabled'])
            self._cancel_btn.state(['disabled'])

    # -- Tree helpers -----------------------------------------------------

    def _row_tag(self, e) -> str:
        if not e.metadata.get('av_clean', True):
            return 'threat'
        if not e.health_ok:
            return 'bad'
        if e.is_duplicate:
            return 'dup'
        if e.ai_description:
            return 'ok'
        return 'pend'

    def _row_status(self, e) -> str:
        if not e.metadata.get('av_clean', True):
            return STATUS_ICON['threat']
        if not e.health_ok:
            return STATUS_ICON['corrupt']
        if e.is_duplicate:
            return STATUS_ICON['duplicate']
        if e.ai_description:
            return STATUS_ICON['ok']
        return STATUS_ICON['pending']

    def _row_add(self, e) -> None:
        iid = str(id(e))
        self._tree.insert('', 'end', iid=iid,
                          values=(FILE_ICONS.get(e.file_type, '\U0001f4c1'),
                                  e.path.name, _human(e.size_bytes),
                                  self._row_status(e)),
                          tags=(self._row_tag(e),))

    def _row_upd(self, e) -> None:
        iid = str(id(e))
        try:
            self._tree.item(iid,
                            values=(FILE_ICONS.get(e.file_type, '\U0001f4c1'),
                                    e.path.name, _human(e.size_bytes),
                                    self._row_status(e)),
                            tags=(self._row_tag(e),))
        except Exception:
            pass

    # -- Preview ----------------------------------------------------------

    def _on_select(self, _=None) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        for e in self._entries:
            if str(id(e)) == iid:
                self._selected = e
                self._show_preview(e)
                break

    def _show_preview(self, e) -> None:
        self._thumb.config(image='', text='')
        self._thumb_hint.config(text='')
        if e.file_type == 'image':
            self._load_img_thumb(e.path)
        elif e.file_type == 'video':
            self._load_vid_thumb(e.path)
        else:
            self._thumb_hint.config(
                text=f"{FILE_ICONS.get(e.file_type, '\U0001f4c1')}  {e.file_type.upper()}")
        self._info_name.config(text=e.path.name)
        parts = [e.file_type, _human(e.size_bytes)]
        if e.date:
            parts.append(e.date.strftime('%Y-%m-%d %H:%M'))
        if e.metadata.get('width'):
            parts.append(f"{e.metadata['width']}×{e.metadata['height']}")
        if e.metadata.get('duration_s'):
            parts.append(f"{e.metadata['duration_s']:.0f}s")
        self._info_meta.config(text='  ·  '.join(parts))
        if e.health_ok:
            self._info_health.config(text='✓  Healthy', fg=GREEN)
        else:
            self._info_health.config(text='✕  ' + '; '.join(e.health_issues), fg=RED)
        if 'av_clean' in e.metadata:
            if e.metadata['av_clean']:
                self._info_av.config(text=f"☠  Clean ({e.metadata['av_engine']})", fg=GREEN)
            else:
                self._info_av.config(
                    text=f"☠  THREAT: {e.metadata.get('av_threat', 'unknown')} "
                         f"({e.metadata['av_engine']})", fg=PURPLE)
        else:
            self._info_av.config(text='', fg=MUTED)
        self._desc.config(state='normal')
        self._desc.delete('1.0', 'end')
        self._desc.insert('1.0', e.ai_description or '')
        self._desc.config(state='disabled')
        self._proposed.set(e.proposed_name or e.path.stem)
        self._nb.select(0)

    def _load_img_thumb(self, path: Path) -> None:
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((480, 200), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb.config(image=photo)
            self._thumb._photo = photo  # type: ignore[attr-defined]
        except Exception as exc:
            self._thumb_hint.config(text=f'Cannot preview: {exc}')

    def _load_vid_thumb(self, path: Path) -> None:
        try:
            import cv2
            from PIL import Image, ImageTk
            cap = cv2.VideoCapture(str(path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            cap.release()
            if not ret:
                self._thumb_hint.config(text='Cannot extract frame')
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img.thumbnail((480, 200), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb.config(image=photo)
            self._thumb._photo = photo  # type: ignore[attr-defined]
            self._thumb_hint.config(text='▶  Video keyframe @ 5s')
        except Exception as exc:
            self._thumb_hint.config(text=f'Cannot preview: {exc}')

    def _save_edit(self) -> None:
        if self._selected:
            self._selected.proposed_name = self._proposed.get().strip()
            self._selected.ai_description = self._desc.get('1.0', 'end').strip()
            self._row_upd(self._selected)

    # -- Tab refreshers ---------------------------------------------------

    def _refresh_dups(self) -> None:
        self._dup_tree.delete(*self._dup_tree.get_children())
        if not self._dup_groups:
            self._dup_hdr.config(text='No duplicates found.')
            return
        total = sum(len(g) for g in self._dup_groups.values())
        self._dup_hdr.config(
            text=f'{len(self._dup_groups)} groups, {total} files — these can be safely deduplicated.')
        for key, group in self._dup_groups.items():
            gtype = 'Exact' if key.startswith('exact') else 'Near-match'
            short_key = key[-6:]
            for i, e in enumerate(group):
                label = f'{gtype} #{short_key}' if i == 0 else ''
                self._dup_tree.insert('', 'end',
                                      values=(label, e.path.name, _human(e.size_bytes)))

    def _refresh_threats(self, summary: dict) -> None:
        self._threat_tree.delete(*self._threat_tree.get_children())
        engine = summary.get('engine', 'unknown')
        scanned = summary.get('scanned', 0)
        threats = summary.get('threats', 0)
        self._threat_engine_lbl.config(
            text=f'Engine: {engine}  |  Scanned: {scanned}  |  Threats: {threats}')
        if not summary.get('threat_files'):
            self._threat_hdr.config(text='✓  All files scanned clean.')
            return
        self._threat_hdr.config(text=f'☠  {threats} threat(s) found — do NOT open these files.')
        for item in summary['threat_files']:
            p = Path(item['path'])
            self._threat_tree.insert('', 'end',
                                     values=(p.name, item['threat']),
                                     tags=('threat',))

    def _refresh_storage(self) -> None:
        if not self._report:
            return
        from . import reporter as rp
        txt = rp.format_report(self._report)
        self._storage_txt.config(state='normal')
        self._storage_txt.delete('1.0', 'end')
        self._storage_txt.insert('1.0', txt)
        self._storage_txt.config(state='disabled')
        self._draw_chart()

    def _draw_chart(self) -> None:
        c = self._chart
        c.delete('all')
        bt = self._report.get('by_type', {})
        if not bt:
            return
        self.update_idletasks()
        W = c.winfo_width() or 600
        H = 170
        pad_l, pad_b, pad_t = 12, 32, 14
        n = len(bt)
        bar_w = max(30, (W - 2 * pad_l) // max(n, 1) - 12)
        max_sz = max(v['size'] for v in bt.values()) or 1
        colors = [ACCENT, '#4fc3f7', '#81c784', '#ffb74d', '#ce93d8', '#80cbc4']
        avail_h = H - pad_t - pad_b
        for i, (t, info) in enumerate(sorted(bt.items(), key=lambda x: -x[1]['size'])):
            x = pad_l + i * (bar_w + 12)
            bar_h = max(4, int(info['size'] / max_sz * avail_h))
            y1, y2 = H - pad_b - bar_h, H - pad_b
            col = colors[i % len(colors)]
            c.create_rectangle(x, y1, x + bar_w, y2, fill=col, outline='', width=0)
            c.create_text(x + bar_w // 2, y2 + 4, text=t, fill=MUTED,
                          font=('Segoe UI', 8), anchor='n')
            c.create_text(x + bar_w // 2, y1 - 3, text=_human(info['size']),
                          fill=TEXT, font=('Segoe UI', 8), anchor='s')

    # -- Apply / Export ---------------------------------------------------

    def _apply_all(self) -> None:
        if not self._entries:
            messagebox.showinfo('Nothing to do', 'Run a scan first.')
            return
        from . import organizer as org
        out = Path(self._output_var.get()).resolve()
        mode = self._mode.get()
        moves = org.plan_moves(self._entries, out, mode)
        if not self._apply_var.get():
            lines = [f'{e.path.name}  ->  {str(d.relative_to(out.parent))}'
                     for e, d in moves[:30]]
            if len(moves) > 30:
                lines.append(f'... and {len(moves) - 30} more')
            messagebox.showinfo('Dry Run Preview',
                                f'Dry-run: {len(moves)} moves planned:\n\n' +
                                '\n'.join(lines) +
                                '\n\nTick "Apply moves" in the toolbar to execute.')
            return
        if not messagebox.askyesno('Confirm Move',
                                   f'Move {len(self._entries)} files into:\n{out}\n\n'
                                   'This cannot be undone easily. Continue?'):
            return

        def _do() -> None:
            self._q.put(('status', f'Moving {len(moves)} files…'))
            results = org.apply_moves(moves, dry_run=False)
            ok = sum(1 for _, _, s, _ in results if s)
            self._q.put(('status', f'Done — {ok}/{len(moves)} files moved to {out}'))

        threading.Thread(target=_do, daemon=True).start()

    def _exp_json(self) -> None:
        if not self._entries:
            messagebox.showinfo('No data', 'Run a scan first.')
            return
        from . import exporter as ex
        p = filedialog.asksaveasfilename(defaultextension='.json',
                                         filetypes=[('JSON', '*.json')],
                                         initialfile='manifest.json')
        if p:
            ex.export_json(self._entries, self._report, Path(p))
            messagebox.showinfo('Exported', f'JSON manifest saved:\n{p}')

    def _exp_csv(self) -> None:
        if not self._entries:
            messagebox.showinfo('No data', 'Run a scan first.')
            return
        from . import exporter as ex
        p = filedialog.asksaveasfilename(defaultextension='.csv',
                                         filetypes=[('CSV', '*.csv')],
                                         initialfile='manifest.csv')
        if p:
            ex.export_csv(self._entries, Path(p))
            messagebox.showinfo('Exported', f'CSV saved:\n{p}')

    def _exp_html(self) -> None:
        if not self._entries:
            messagebox.showinfo('No data', 'Run a scan first.')
            return
        from . import exporter as ex
        p = filedialog.askdirectory(title='Select output folder for HTML gallery')
        if p:
            ex.export_html(self._entries, self._report, Path(p))
            messagebox.showinfo('Exported', f'HTML gallery saved:\n{p}\\index.html')


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()
