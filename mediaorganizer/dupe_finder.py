import os, re, math, time, shutil, threading, queue, subprocess, urllib.parse, traceback
from dataclasses import dataclass
from typing import Optional, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(SCRIPT_DIR, "dupe_gui_crash.log")
def _log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

USE_TTKBOOTSTRAP = True
try:
    import ttkbootstrap as tb
except Exception:
    USE_TTKBOOTSTRAP = False
    tb = None

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
from PIL import Image, ImageTk, ImageChops, ImageEnhance, ImageFilter
import imagehash

try:
    from send2trash import send2trash
except Exception:
    send2trash = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}

try:
    RESAMPLE_BILINEAR = Image.Resampling.BILINEAR
except Exception:
    RESAMPLE_BILINEAR = Image.BILINEAR

def human_bytes(n: int) -> str:
    step = 1024.0
    f = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if f < step:
            return f"{f:.1f}{unit}"
        f /= step
    return f"{f:.1f}PB"

def safe_getsize(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0

def open_image_rgb(path: str):
    with Image.open(path) as im:
        im.load()
        return im.convert("RGB"), im

def compute_phash(path: str):
    try:
        im_rgb, _ = open_image_rgb(path)
        return imagehash.phash(im_rgb)
    except Exception:
        return None

def downscale_gray(im_rgb: Image.Image, max_side=256) -> np.ndarray:
    w, h = im_rgb.size
    scale = max(w, h) / float(max_side)
    if scale > 1:
        nw, nh = max(1, int(w / scale)), max(1, int(h / scale))
        im_rgb = im_rgb.resize((nw, nh), RESAMPLE_BILINEAR)
    return (np.asarray(im_rgb.convert("L"), dtype=np.float32) / 255.0)

def ssim_global(a: np.ndarray, b: np.ndarray) -> float:
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a = a[:h, :w]
    b = b[:h, :w]
    mu_a = a.mean()
    mu_b = b.mean()
    sigma_a = a.var()
    sigma_b = b.var()
    sigma_ab = ((a - mu_a) * (b - mu_b)).mean()
    c1 = 0.01 ** 2
    c2 = 0.03 ** 2
    den = (mu_a**2 + mu_b**2 + c1) * (sigma_a + sigma_b + c2)
    if den == 0:
        return 0.0
    num = (2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)
    return float(num / den)

def sharpness_score(gray01: np.ndarray) -> float:
    g = gray01
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    center = g[1:-1, 1:-1]
    lap = (-4 * center + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())

def jpeg_quality_guess(pil_im) -> Optional[str]:
    try:
        if (getattr(pil_im, "format", "") or "").upper() != "JPEG":
            return None
        q = getattr(pil_im, "quantization", None)
        if not q:
            return None
        vals = []
        for _, table in q.items():
            vals.extend(table)
        avg = float(sum(vals)) / max(1, len(vals))
        if avg <= 8:  return "very high"
        if avg <= 16: return "high"
        if avg <= 32: return "medium"
        if avg <= 64: return "low"
        return "very low"
    except Exception:
        return None

def phash_similarity_percent(h1, h2):
    d = int(h1 - h2)
    pct = max(0.0, (1.0 - (d / 64.0)) * 100.0)
    return pct, d

def bucket_key(h):
    return str(h)[:4]

def make_difference_image(path_a: str, path_b: str) -> Image.Image:
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, RESAMPLE_BILINEAR)
    diff = ImageChops.difference(a, b)
    diff = ImageEnhance.Contrast(diff).enhance(3.0)
    diff = ImageEnhance.Brightness(diff).enhance(1.4)
    return diff

def make_heatmap_image(path_a: str, path_b: str) -> Image.Image:
    diff = make_difference_image(path_a, path_b).convert("RGB")
    r, g, b = diff.split()
    r = ImageEnhance.Brightness(r).enhance(1.6)
    g = ImageEnhance.Brightness(g).enhance(0.5)
    b = ImageEnhance.Brightness(b).enhance(0.5)
    return Image.merge("RGB", (r, g, b))

def make_edges_image(path_a: str, path_b: str) -> Image.Image:
    a = Image.open(path_a).convert("RGB")
    b = Image.open(path_b).convert("RGB")
    if b.size != a.size:
        b = b.resize(a.size, RESAMPLE_BILINEAR)
    diff = ImageChops.difference(a, b).convert("L")
    diff = diff.filter(ImageFilter.FIND_EDGES)
    diff = ImageEnhance.Contrast(diff).enhance(3.0)
    return diff.convert("RGB")

_DUPENAME_RE = re.compile(r"(\(\d+\))|\bcopy\b|\bduplicate\b|\bdup\b|\bedited\b", re.I)

def duplicate_name_penalty(filename: str) -> float:
    return 0.35 if _DUPENAME_RE.search(filename or "") else 0.0

def suggest_delete_score(img: "ImgInfo") -> float:
    return score_best(img) - duplicate_name_penalty(os.path.basename(img.path))

def should_ignore(path: str, ignore_folder_names: set, ignore_name_patterns: list, exts_allowed: set) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext not in exts_allowed:
        return True
    parts = [p.lower() for p in os.path.normpath(path).split(os.sep)]
    for name in ignore_folder_names:
        if name.lower() in parts:
            return True
    base = os.path.basename(path)
    for pat in ignore_name_patterns:
        if pat.search(base):
            return True
    return False

def iter_images_filtered(root: str, ignore_folder_names: set, ignore_name_patterns: list):
    ignore_lc = {x.lower() for x in ignore_folder_names}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d.lower() not in ignore_lc]
        for f in files:
            path = os.path.join(base, f)
            if should_ignore(path, ignore_folder_names, ignore_name_patterns, IMAGE_EXTS):
                continue
            yield path

def reveal_in_explorer(path: str):
    try:
        subprocess.Popen(["explorer.exe", "/select,", os.path.normpath(path)], shell=False)
    except Exception:
        try:
            os.startfile(os.path.dirname(path))
        except Exception:
            pass

def copy_to_clipboard(root_tk: tk.Tk, text: str):
    try:
        root_tk.clipboard_clear()
        root_tk.clipboard_append(text)
        root_tk.update_idletasks()
    except Exception:
        pass

def find_chrome_exe():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def open_url(url: str, incognito: bool):
    chrome = find_chrome_exe()
    if chrome and incognito:
        subprocess.Popen([chrome, "--incognito", url], shell=False)
    else:
        os.startfile(url)

def lens_url(): return "https://lens.google.com/upload"
def tineye_url(): return "https://tineye.com/"
def bing_visual_url(): return "https://www.bing.com/visualsearch"

def google_images_query_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://www.google.com/search?tbm=isch&q={q}"

@dataclass
class ImgInfo:
    path: str
    phash: object = None
    size_b: int = 0
    w: int = 0
    h: int = 0
    fmt: str = ""
    jpeg_q: Optional[str] = None
    sharp: float = 0.0
    gray256: Optional[np.ndarray] = None

    @property
    def pixels(self):
        return self.w * self.h

def score_best(img: ImgInfo) -> float:
    fmt = (img.fmt or "").upper()
    fmt_bonus = 0.15 if fmt in ("PNG", "TIFF") else (0.10 if fmt == "WEBP" else (0.05 if fmt == "JPEG" else 0.0))
    jq_bonus = {"very high": 0.10, "high": 0.07, "medium": 0.03, "low": -0.02, "very low": -0.05}.get(img.jpeg_q, 0.0)
    pix_term = math.log10(max(1, img.pixels))
    size_term = math.log10(max(1, img.size_b))
    sharp_term = math.log10(1.0 + max(0.0, img.sharp) * 1e4)
    return (2.2 * pix_term) + (1.2 * size_term) + (0.8 * sharp_term) + fmt_bonus + jq_bonus

def ensure_meta(item: ImgInfo, heavy=True):
    if item.size_b == 0:
        item.size_b = safe_getsize(item.path)
    if item.w and item.h and item.fmt and (not heavy or item.gray256 is not None):
        return
    try:
        im_rgb, im_raw = open_image_rgb(item.path)
        item.w, item.h = im_rgb.size
        item.fmt = getattr(im_raw, "format", "") or ""
        if heavy:
            item.gray256 = downscale_gray(im_rgb, 256)
            item.sharp = sharpness_score(item.gray256)
            item.jpeg_q = jpeg_quality_guess(im_raw)
    except Exception:
        pass

def build_groups(items, phash_thresh, refine_ssim, ssim_min, stop_evt=None, progress=None):
    buckets = {}
    for it in items:
        if it.phash is None:
            continue
        buckets.setdefault(bucket_key(it.phash), []).append(it)
    groups = []
    visited = set()
    bucket_items = list(buckets.items())
    total = len(bucket_items)
    for bi, (_bk, arr) in enumerate(bucket_items, start=1):
        if stop_evt and stop_evt.is_set():
            break
        if progress:
            progress(f"Grouping {bi}/{total}", 70, "")
        n = len(arr)
        if n < 2:
            continue
        for i in range(n):
            seed = arr[i]
            if seed.path in visited:
                continue
            grp = [seed]
            visited.add(seed.path)
            for j in range(i + 1, n):
                other = arr[j]
                if other.path in visited:
                    continue
                _, dist = phash_similarity_percent(seed.phash, other.phash)
                if dist <= phash_thresh:
                    grp.append(other)
                    visited.add(other.path)
            if len(grp) <= 1:
                continue
            if refine_ssim:
                best = max(grp, key=score_best)
                refined = [best]
                for x in grp:
                    if x is best:
                        continue
                    if best.gray256 is None or x.gray256 is None:
                        refined.append(x)
                        continue
                    s = ssim_global(best.gray256, x.gray256)
                    if max(0.0, s) * 100.0 >= ssim_min:
                        refined.append(x)
                grp = refined
            if len(grp) > 1:
                groups.append(grp)
    groups.sort(key=lambda g: len(g), reverse=True)
    return groups

class GroupCard(ttk.Frame):
    def __init__(self, parent, group_index, thumb_base, title, subtitle, count, on_open):
        super().__init__(parent, padding=10)
        self.group_index = group_index
        self.on_open = on_open
        self.base_px = 150
        self.hover_scale = 1.18
        self.anim_ms = 11
        self.anim_steps = 12
        self._anim_after_id = None
        self._anim_token = 0
        self._cur_scale = 1.0
        self._src = thumb_base.copy().convert("RGB")
        max_needed = int(self.base_px * self.hover_scale) + 12
        if max(self._src.size) < max_needed:
            self._src = self._src.resize((max_needed, max_needed), RESAMPLE_BILINEAR)
        self._border = tk.Frame(self, highlightthickness=2, highlightbackground="#d0d0d0", bd=0)
        self._border.pack(fill=tk.BOTH, expand=True)
        self._inner = ttk.Frame(self._border, padding=10)
        self._inner.pack(fill=tk.BOTH, expand=True)
        self.img = ttk.Label(self._inner)
        self.img.pack()
        self.badge = ttk.Label(self._inner, text=f"{count} items", font=("Segoe UI", 9, "bold"))
        self.badge.pack(anchor="w", pady=(8, 0))
        self.t1 = ttk.Label(self._inner, text=title, font=("Segoe UI", 10, "bold"), wraplength=240, justify="left")
        self.t1.pack(anchor="w", pady=(4, 0))
        self.t2 = ttk.Label(self._inner, text=subtitle, wraplength=240, justify="left")
        self.t2.pack(anchor="w", pady=(2, 0))
        self._render(1.0)
        for w in (self, self._border, self._inner, self.img, self.badge, self.t1, self.t2):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

    def _on_enter(self, _e=None):
        self._border.configure(highlightbackground="#3b82f6")
        self._animate_to(self.hover_scale)

    def _on_leave(self, _e=None):
        self._border.configure(highlightbackground="#d0d0d0")
        self._animate_to(1.0)

    def _on_click(self, _e=None):
        self.on_open(self.group_index)

    def _ease_out_cubic(self, t):
        return 1.0 - (1.0 - t) ** 3

    def _render(self, scale):
        px = max(48, int(self.base_px * scale))
        im = self._src.copy()
        im.thumbnail((px, px), RESAMPLE_BILINEAR)
        self._tk = ImageTk.PhotoImage(im)
        self.img.configure(image=self._tk)

    def _cancel_anim(self):
        if self._anim_after_id is not None:
            try:
                self.after_cancel(self._anim_after_id)
            except Exception:
                pass
        self._anim_after_id = None

    def _animate_to(self, target_scale):
        self._cancel_anim()
        self._anim_token += 1
        token = self._anim_token
        start = float(self._cur_scale)
        end = float(target_scale)
        steps = int(self.anim_steps)
        if abs(end - start) < 0.004:
            self._cur_scale = end
            self._render(end)
            return
        i = 0
        def step():
            nonlocal i
            if token != self._anim_token:
                return
            i += 1
            t = min(1.0, i / steps)
            eased = self._ease_out_cubic(t)
            s = start + (end - start) * eased
            self._cur_scale = s
            self._render(s)
            if i < steps:
                self._anim_after_id = self.after(self.anim_ms, step)
            else:
                self._anim_after_id = None
        step()

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = ttk.Frame(self.canvas)
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.win, width=e.width))

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        if USE_TTKBOOTSTRAP and tb is not None:
            try:
                tb.Style("flatly")
            except Exception as e:
                _log("Theme init failed: " + repr(e))
        self.title("Offline Duplicate Finder")
        self.geometry("1600x980")
        self.minsize(1280, 780)
        self.work_q = queue.Queue()
        self.stop_evt = threading.Event()
        self.root_dir = tk.StringVar(value="")
        self.phash_thresh = tk.IntVar(value=8)
        self.refine_ssim = tk.BooleanVar(value=True)
        self.ssim_min = tk.DoubleVar(value=85.0)
        self.incognito = tk.BooleanVar(value=True)
        self.ignore_folders = tk.StringVar(value="_DUPES;_REVIEW;thumbnails;thumb;cache;.git")
        self.ignore_names = tk.StringVar(value=r".*\.tmp$;.*\.part$;.*_thumb\..*")
        self.items: List[ImgInfo] = []
        self.groups: List[List[ImgInfo]] = []
        self.group_idx: Optional[int] = None
        self.selected = set()
        self.compare_a: Optional[str] = None
        self.compare_b: Optional[str] = None
        self.suggested = set()
        self._preview_refs = []
        self._detail_thumb_refs: List[ImageTk.PhotoImage] = []
        self._build()
        self.after(60, self._poll)

    def _build(self):
        pad = 10
        top = ttk.Frame(self, padding=pad)
        top.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(top, text="Offline Duplicate Finder", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        ttk.Checkbutton(top, text="Incognito", variable=self.incognito).pack(side=tk.LEFT, padx=(14, 0))
        ttk.Button(top, text="Stop", command=self.on_stop).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(top, text="Scan", command=self.on_scan).pack(side=tk.RIGHT, padx=(8, 0))
        folder = ttk.Frame(self, padding=(pad, 0, pad, pad))
        folder.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(folder, text="Folder", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Entry(folder, textvariable=self.root_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Button(folder, text="Browse", command=self.on_browse).pack(side=tk.LEFT)
        settings = ttk.Frame(self, padding=(pad, 0, pad, pad))
        settings.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(settings, text="pHash <=").pack(side=tk.LEFT)
        ttk.Spinbox(settings, from_=0, to=20, textvariable=self.phash_thresh, width=5).pack(side=tk.LEFT, padx=(6, 14))
        ttk.Checkbutton(settings, text="SSIM refine", variable=self.refine_ssim).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Label(settings, text="SSIM % >=").pack(side=tk.LEFT)
        ttk.Spinbox(settings, from_=0, to=100, increment=1, textvariable=self.ssim_min, width=6).pack(side=tk.LEFT, padx=(6, 14))
        ignore = ttk.Labelframe(self, text="Ignore rules", padding=(pad, 6))
        ignore.pack(side=tk.TOP, fill=tk.X, padx=pad, pady=(0, pad))
        ttk.Label(ignore, text="Folders (semicolon separated)").grid(row=0, column=0, sticky="w")
        ttk.Entry(ignore, textvariable=self.ignore_folders).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(ignore, text="Names regex (semicolon separated)").grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Entry(ignore, textvariable=self.ignore_names).grid(row=1, column=1, sticky="ew", padx=10, pady=(6,0))
        ignore.columnconfigure(1, weight=1)
        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(0, pad))
        left_area = ttk.Frame(main_pane, padding=pad)
        right_area = ttk.Frame(main_pane, padding=pad)
        main_pane.add(left_area, weight=3)
        main_pane.add(right_area, weight=2)
        left_stack = ttk.Frame(left_area)
        left_stack.pack(fill=tk.BOTH, expand=True)
        self.screen_carousel = ttk.Frame(left_stack)
        self.screen_detail = ttk.Frame(left_stack)
        for f in (self.screen_carousel, self.screen_detail):
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._build_carousel_screen()
        self._build_detail_screen()
        self.show_carousel()
        right_pane = ttk.Panedwindow(right_area, orient=tk.VERTICAL)
        right_pane.pack(fill=tk.BOTH, expand=True)
        self.preview_panel = ttk.Frame(right_pane, padding=10)
        self.controls_panel = ttk.Frame(right_pane, padding=10)
        right_pane.add(self.preview_panel, weight=3)
        right_pane.add(self.controls_panel, weight=2)
        self._build_preview_panel()
        self._build_controls_panel()
        bottom = ttk.Frame(self, padding=pad)
        bottom.pack(side=tk.BOTTOM, fill=tk.X)
        self.status = ttk.Label(bottom, text="Idle")
        self.status.pack(side=tk.LEFT)
        self.prog = ttk.Progressbar(bottom, mode="determinate", length=360)
        self.prog.pack(side=tk.RIGHT)

    def _build_carousel_screen(self):
        head = ttk.Frame(self.screen_carousel, padding=(0, 0, 0, 10))
        head.pack(fill=tk.X)
        self.carousel_title = ttk.Label(head, text="No scan yet", font=("Segoe UI", 12, "bold"))
        self.carousel_title.pack(side=tk.LEFT)
        bar = ttk.Frame(self.screen_carousel)
        bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(bar, text="<", command=lambda: self._carousel_scroll(-1)).pack(side=tk.LEFT)
        ttk.Button(bar, text=">", command=lambda: self._carousel_scroll(1)).pack(side=tk.RIGHT)
        self.carousel_canvas = tk.Canvas(self.screen_carousel, height=330, highlightthickness=0)
        self.carousel_canvas.pack(fill=tk.X, expand=False)
        self.carousel_inner = ttk.Frame(self.carousel_canvas)
        self.carousel_win = self.carousel_canvas.create_window((0, 0), window=self.carousel_inner, anchor="nw")
        self.carousel_inner.bind("<Configure>", lambda _e=None: self.carousel_canvas.configure(scrollregion=self.carousel_canvas.bbox("all")))
        self.carousel_canvas.bind("<Configure>", lambda e: self.carousel_canvas.itemconfig(self.carousel_win, height=e.height))
        self.carousel_canvas.bind_all("<Shift-MouseWheel>", self._on_shift_wheel)
        ttk.Label(self.screen_carousel, text="Hover to peek * Click a card to open").pack(fill=tk.X, pady=(10, 0))

    def _build_detail_screen(self):
        top = ttk.Frame(self.screen_detail, padding=(0, 0, 0, 10))
        top.pack(fill=tk.X)
        ttk.Button(top, text="X Back", command=self.show_carousel).pack(side=tk.LEFT)
        self.detail_title = ttk.Label(top, text="Group", font=("Segoe UI", 12, "bold"))
        self.detail_title.pack(side=tk.LEFT, padx=(10, 0))
        self.detail_scroll = ScrollableFrame(self.screen_detail)
        self.detail_scroll.pack(fill=tk.BOTH, expand=True)

    def _build_preview_panel(self):
        ttk.Label(self.preview_panel, text="Compare / Preview", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.ab_label = ttk.Label(self.preview_panel, text="A: -\nB: -", justify="left")
        self.ab_label.pack(anchor="w", pady=(0, 6))
        topbar = ttk.Frame(self.preview_panel)
        topbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(topbar, text="View").pack(side=tk.LEFT)
        self.view_mode = tk.StringVar(value="Side-by-side")
        self.view_combo = ttk.Combobox(topbar, textvariable=self.view_mode,
            values=["Side-by-side", "Diff", "Heatmap", "Edges"], state="readonly", width=14)
        self.view_combo.pack(side=tk.LEFT, padx=(8, 0))
        self.view_combo.bind("<<ComboboxSelected>>", lambda _e=None: self._update_preview())
        self.sim_label = ttk.Label(topbar, text="", justify="right")
        self.sim_label.pack(side=tk.RIGHT)
        self.preview1 = ttk.Label(self.preview_panel)
        self.preview1.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        self.preview2 = ttk.Label(self.preview_panel)
        self.preview2.pack(fill=tk.BOTH, expand=True)
        ttk.Label(self.preview_panel,
            text="Tip: Right-click to set A then B. Left-click toggles selection for Delete/Move.",
            justify="left").pack(anchor="w", pady=(10, 0))

    def _build_controls_panel(self):
        filetools = ttk.Labelframe(self.controls_panel, text="File tools", padding=10)
        filetools.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(filetools, text="Reveal in Explorer", command=self.on_reveal_current).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(filetools, text="Copy Full Path", command=self.on_copy_path).pack(fill=tk.X, pady=(0, 6))
        web = ttk.Labelframe(self.controls_panel, text="Online search (manual drag-drop)", padding=10)
        web.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(web, text="Search -> Google Lens", command=lambda: self.on_search_image("lens")).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(web, text="Search -> Bing Visual", command=lambda: self.on_search_image("bing")).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(web, text="Search -> TinEye", command=lambda: self.on_search_image("tineye")).pack(fill=tk.X, pady=(0, 10))
        ttk.Button(web, text="Find Larger (Incognito)", command=self.on_find_larger).pack(fill=tk.X)
        ttk.Label(web, text="When the site opens, drag the file from Explorer into the page.\n(We reveal + copy the path for you.)", justify="left").pack(anchor="w", pady=(10, 0))
        actions = ttk.Labelframe(self.controls_panel, text="Actions", padding=10)
        actions.pack(fill=tk.X)
        ttk.Button(actions, text="Move Selected -> _REVIEW", command=self.on_move_selected_review).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(actions, text="Delete Selected -> Recycle Bin", command=self.on_delete_recycle).pack(fill=tk.X)
        ttk.Button(actions, text="Select Suggested Deletes", command=self.on_select_suggested).pack(fill=tk.X, pady=(10, 0))

    def show_carousel(self):
        self.screen_carousel.lift()
        self.selected.clear()
        self.compare_a = None
        self.compare_b = None
        self._update_preview()

    def _on_shift_wheel(self, e):
        self._carousel_scroll(-1 if e.delta > 0 else 1)

    def _carousel_scroll(self, direction):
        self.carousel_canvas.xview_scroll(12 * direction, "units")

    def _current_group(self):
        if self.group_idx is None or self.group_idx < 0 or self.group_idx >= len(self.groups):
            return None
        return self.groups[self.group_idx]

    def open_group_from_carousel(self, group_index):
        if group_index < 0 or group_index >= len(self.groups):
            return
        self.group_idx = group_index
        self.selected.clear()
        self.compare_a = None
        self.compare_b = None
        self.render_group_detail()
        self.screen_detail.lift()

    def _render_carousel(self):
        for w in self.carousel_inner.winfo_children():
            w.destroy()
        if not self.groups:
            self.carousel_title.config(text="No duplicate groups found")
            return
        self.carousel_title.config(text=f"Duplicate groups: {len(self.groups)}")
        row = ttk.Frame(self.carousel_inner)
        row.pack(side=tk.TOP, fill=tk.X)
        for gi, grp in enumerate(self.groups):
            rep = max(grp, key=score_best)
            ensure_meta(rep, heavy=True)
            try:
                im = Image.open(rep.path).convert("RGB")
            except Exception:
                im = Image.new("RGB", (256, 256), (90, 90, 90))
            title = f"Group {gi+1}"
            subtitle = f"{len(grp)} items * {rep.w}x{rep.h} * {human_bytes(rep.size_b)}"
            card = GroupCard(row, gi, im, title, subtitle, count=len(grp), on_open=self.open_group_from_carousel)
            card.pack(side=tk.LEFT, padx=12, pady=10)

    def render_group_detail(self):
        for w in self.detail_scroll.inner.winfo_children():
            w.destroy()
        grp = self._current_group()
        if not grp:
            self.detail_title.config(text="No group"); return
        gid = (self.group_idx or 0) + 1
        self.detail_title.config(text=f"Group {gid} * {len(grp)} items")
        ordered = sorted(grp, key=score_best, reverse=True)
        best_keep = max(grp, key=suggest_delete_score)
        self.suggested = {x.path for x in grp if x.path != best_keep.path}
        cols = 4
        thumb = 160
        self._detail_thumb_refs = []
        for i, item in enumerate(ordered):
            ensure_meta(item, heavy=True)
            r = i // cols; c = i % cols
            p = item.path
            is_sel = (p in self.selected)
            is_a = (p == self.compare_a)
            is_b = (p == self.compare_b)
            border = "#3b82f6" if is_a else ("#a855f7" if is_b else ("#f59e0b" if is_sel else ("#ef4444" if (p in self.suggested) else "#d0d0d0")))
            outer = tk.Frame(self.detail_scroll.inner, highlightthickness=3, highlightbackground=border, bd=0)
            outer.grid(row=r, column=c, sticky="nsew", padx=10, pady=10)
            card = ttk.Frame(outer, padding=10); card.pack(fill=tk.BOTH, expand=True)
            tag_txt = "A" if is_a else ("B" if is_b else ("SUGGEST" if (p in self.suggested) else ""))
            if tag_txt:
                tag_bg = "#3b82f6" if is_a else ("#a855f7" if is_b else "#ef4444")
                tag = tk.Label(outer, text=tag_txt, bg=tag_bg, fg="white", padx=6, pady=1, font=("Segoe UI", 8, "bold"))
                tag.place(relx=1.0, rely=0.0, x=-6, y=6, anchor="ne")
            try:
                im = Image.open(p).convert("RGB"); im.thumbnail((thumb, thumb), RESAMPLE_BILINEAR)
            except Exception:
                im = Image.new("RGB", (thumb, thumb), (70, 70, 70))
            tkimg = ImageTk.PhotoImage(im); self._detail_thumb_refs.append(tkimg)
            img_lbl = ttk.Label(card, image=tkimg); img_lbl.pack()
            ttk.Label(card, text=os.path.basename(p), wraplength=220, justify="left", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8,0))
            ttk.Label(card, text=f"{item.w}x{item.h} * {human_bytes(item.size_b)} * {(item.fmt or '').upper()}",
                      wraplength=220, justify="left").pack(anchor="w")
            ttk.Label(card, text=f"JPEG {item.jpeg_q or '-'} * Sharp {item.sharp:.5f}",
                      wraplength=220, justify="left").pack(anchor="w")
            def left_click(path=p):
                def _cb(_e=None):
                    if path in self.selected: self.selected.remove(path)
                    else: self.selected.add(path)
                    self._update_preview(); self.render_group_detail()
                return _cb
            def right_click(path=p):
                def _cb(_e=None):
                    if self.compare_a is None: self.compare_a = path
                    elif self.compare_b is None and path != self.compare_a: self.compare_b = path
                    else:
                        self.compare_a = path; self.compare_b = None
                    self._update_preview(); self.render_group_detail()
                return _cb
            for wdg in (outer, card, img_lbl):
                wdg.bind("<Button-1>", left_click())
                wdg.bind("<Button-3>", right_click())
        self._update_preview()

    def current_path(self):
        if self.compare_a and os.path.exists(self.compare_a): return self.compare_a
        if self.selected:
            p = next(iter(self.selected))
            if os.path.exists(p): return p
        grp = self._current_group()
        if not grp: return None
        return max(grp, key=score_best).path

    def on_reveal_current(self):
        p = self.current_path() or self.compare_b
        if not p: messagebox.showinfo("Reveal", "No file selected."); return
        reveal_in_explorer(p)

    def on_copy_path(self):
        p = self.current_path() or self.compare_b
        if not p: messagebox.showinfo("Copy Path", "No file selected."); return
        copy_to_clipboard(self, p)
        self.status.config(text="Copied full path")

    def on_search_image(self, which):
        p = self.current_path() or self.compare_b
        if not p: messagebox.showinfo("Online search", "Select an image first."); return
        reveal_in_explorer(p); copy_to_clipboard(self, p)
        if which == "lens": open_url(lens_url(), self.incognito.get())
        elif which == "bing": open_url(bing_visual_url(), self.incognito.get())
        else: open_url(tineye_url(), self.incognito.get())

    def on_find_larger(self):
        p = self.current_path() or self.compare_b
        if not p: messagebox.showinfo("Find larger", "Select an image first."); return
        reveal_in_explorer(p); copy_to_clipboard(self, p)
        base = os.path.splitext(os.path.basename(p))[0]
        query = f"{base} high resolution original 4k"
        open_url(lens_url(), self.incognito.get())
        open_url(google_images_query_url(query), self.incognito.get())

    def on_move_selected_review(self):
        grp = self._current_group()
        if not grp or not self.selected: messagebox.showinfo("Move", "Select items first."); return
        root = self.root_dir.get().strip()
        dest_root = os.path.join(root, "_REVIEW"); os.makedirs(dest_root, exist_ok=True)
        gid = (self.group_idx or 0) + 1
        dest_group = os.path.join(dest_root, f"Group_{gid:04d}"); os.makedirs(dest_group, exist_ok=True)
        removed = set()
        for p in list(self.selected):
            try:
                base = os.path.basename(p)
                target = os.path.join(dest_group, base)
                if os.path.exists(target):
                    name, ext = os.path.splitext(base); k = 1
                    while os.path.exists(target):
                        target = os.path.join(dest_group, f"{name}__{k}{ext}"); k += 1
                shutil.move(p, target); removed.add(p)
            except Exception:
                pass
        self._remove_from_model(removed)

    def on_delete_recycle(self):
        grp = self._current_group()
        if not grp or not self.selected: messagebox.showinfo("Delete", "Select items first."); return
        if send2trash is None:
            messagebox.showerror("Missing dependency", "send2trash not installed.\nRun: pip install send2trash")
            return
        if not messagebox.askyesno("Confirm", f"Send {len(self.selected)} files to Recycle Bin?"): return
        removed = set()
        for p in list(self.selected):
            try: send2trash(p); removed.add(p)
            except Exception: pass
        self._remove_from_model(removed)

    def on_select_suggested(self):
        grp = self._current_group()
        if not grp:
            messagebox.showinfo("Suggested deletes", "Open a group first.")
            return
        self.selected = set(self.suggested)
        if self.compare_a in self.selected: self.selected.remove(self.compare_a)
        if self.compare_b in self.selected: self.selected.remove(self.compare_b)
        self.status.config(text=f"Selected suggested deletes: {len(self.selected)}")
        self.render_group_detail()
        self._update_preview()

    def _remove_from_model(self, removed):
        if not removed: return
        self.selected.difference_update(removed)
        if self.compare_a in removed: self.compare_a = None
        if self.compare_b in removed: self.compare_b = None
        new_groups = []
        for g in self.groups:
            ng = [x for x in g if x.path not in removed]
            if len(ng) > 1: new_groups.append(ng)
        self.groups = new_groups
        self._render_carousel()
        if self.group_idx is None: return
        self.group_idx = max(0, min(self.group_idx, len(self.groups) - 1))
        self.render_group_detail()
        self._update_preview()

    def _set_preview(self, lbl, path, max_w=720, max_h=360):
        try:
            im = Image.open(path).convert("RGB"); im.thumbnail((max_w, max_h), RESAMPLE_BILINEAR)
            tkimg = ImageTk.PhotoImage(im)
        except Exception:
            tkimg = ImageTk.PhotoImage(Image.new("RGB", (max_w, max_h), (80, 80, 80)))
        lbl.config(image=tkimg); self._preview_refs.append(tkimg)

    def _update_preview(self):
        if not hasattr(self, 'ab_label') or not hasattr(self, 'preview1') or not hasattr(self, 'preview2'):
            return
        a = self.compare_a; b = self.compare_b
        self.ab_label.config(text=f"A: {os.path.basename(a) if a else '-'}\nB: {os.path.basename(b) if b else '-'}")
        self._preview_refs = []
        if a and b and os.path.exists(a) and os.path.exists(b):
            try:
                im_a, _ = open_image_rgb(a)
                im_b, _ = open_image_rgb(b)
                ga = downscale_gray(im_a, 256)
                gb = downscale_gray(im_b, 256)
                ssim = max(0.0, ssim_global(ga, gb)) * 100.0
            except Exception:
                ssim = 0.0
            try:
                ha = imagehash.phash(Image.open(a).convert("RGB"))
                hb = imagehash.phash(Image.open(b).convert("RGB"))
                ph_pct, ph_dist = phash_similarity_percent(ha, hb)
            except Exception:
                ph_pct, ph_dist = 0.0, 64
            sim_index = (0.60 * ssim) + (0.40 * ph_pct)
            view = self.view_mode.get() if hasattr(self, "view_mode") else "Side-by-side"
            self._set_preview(self.preview1, a)
            if view == "Side-by-side":
                self._set_preview(self.preview2, b)
            elif view == "Diff":
                try:
                    img = make_difference_image(a, b)
                    img.thumbnail((720, 360), RESAMPLE_BILINEAR)
                    tkimg = ImageTk.PhotoImage(img)
                    self.preview2.config(image=tkimg); self._preview_refs.append(tkimg)
                except Exception:
                    self._set_preview(self.preview2, b)
            elif view == "Heatmap":
                try:
                    img = make_heatmap_image(a, b)
                    img.thumbnail((720, 360), RESAMPLE_BILINEAR)
                    tkimg = ImageTk.PhotoImage(img)
                    self.preview2.config(image=tkimg); self._preview_refs.append(tkimg)
                except Exception:
                    self._set_preview(self.preview2, b)
            elif view == "Edges":
                try:
                    img = make_edges_image(a, b)
                    img.thumbnail((720, 360), RESAMPLE_BILINEAR)
                    tkimg = ImageTk.PhotoImage(img)
                    self.preview2.config(image=tkimg); self._preview_refs.append(tkimg)
                except Exception:
                    self._set_preview(self.preview2, b)
            else:
                self._set_preview(self.preview2, b)
            self.sim_label.config(text=f"SSIM {ssim:.1f}% * pHash {ph_pct:.1f}% (d={ph_dist}) * Index {sim_index:.1f}%")
            return
        p = self.current_path()
        if p and os.path.exists(p): self._set_preview(self.preview1, p)
        else: self.preview1.config(image="")
        self.preview2.config(image=""); self.sim_label.config(text="")

    def on_browse(self):
        d = filedialog.askdirectory(title="Choose folder")
        if d:
            self.root_dir.set(d)
            self.on_scan()

    def on_stop(self):
        self.stop_evt.set()
        self.status.config(text="Stopping...")
        self.prog.config(value=0)

    def on_scan(self):
        root = self.root_dir.get().strip()
        if not root or not os.path.isdir(root):
            messagebox.showerror("Folder required", "Choose a valid folder first."); return
        self.stop_evt.clear()
        self.items.clear(); self.groups.clear(); self.group_idx = None
        self.selected.clear(); self.compare_a = None; self.compare_b = None
        self._update_preview()
        self.carousel_title.config(text="Scanning...")
        self.status.config(text="Scanning..."); self.prog.config(value=1)
        threading.Thread(target=self._scan_worker, args=(root,), daemon=True).start()

    def _scan_worker(self, root):
        try:
            ignore_folder_names = {x.strip() for x in self.ignore_folders.get().split(";") if x.strip()}
            pats = []
            for raw in [x.strip() for x in self.ignore_names.get().split(";") if x.strip()]:
                try: pats.append(re.compile(raw, re.I))
                except Exception: pass
            paths = list(iter_images_filtered(root, ignore_folder_names, pats))
            if not paths: self.work_q.put(("done", [])); return
            items = [ImgInfo(path=p, size_b=safe_getsize(p)) for p in paths]
            total = len(items); t0 = time.time()
            for i, it in enumerate(items, start=1):
                if self.stop_evt.is_set(): self.work_q.put(("done", [])); return
                it.phash = compute_phash(it.path); ensure_meta(it, heavy=True)
                elapsed = max(0.001, time.time() - t0)
                rate = i / elapsed
                remaining = (total - i) / max(0.1, rate)
                eta_text = f"{rate:.1f} imgs/s * ETA {int(remaining//60)}m {int(remaining%60)}s"
                pct = int(5 + 55 * (i / total))
                if i % 25 == 0 or i == total:
                    self.work_q.put(("status", f"Hashing... {i}/{total}", pct, eta_text))
            ph = int(self.phash_thresh.get())
            refine = bool(self.refine_ssim.get())
            ssim_min = float(self.ssim_min.get())
            self.work_q.put(("status", "Grouping...", 70, ""))
            groups = build_groups(items, ph, refine, ssim_min, stop_evt=self.stop_evt, progress=None)
            self.items = items
            self.work_q.put(("done", groups))
        except Exception:
            self.work_q.put(("error", traceback.format_exc()))

    def _poll(self):
        try:
            while True:
                kind, *rest = self.work_q.get_nowait()
                if kind == "status":
                    text, pct, eta_text = rest
                    self.status.config(text=f"{text} {('* ' + eta_text) if eta_text else ''}")
                    self.prog.config(value=max(0, min(100, pct)))
                elif kind == "done":
                    self.groups = rest[0]
                    self.prog.config(value=100)
                    self.status.config(text=f"Done * {len(self.groups)} groups")
                    self._render_carousel()
                elif kind == "error":
                    msg = rest[0]
                    _log("ERROR:\n" + msg)
                    self.status.config(text="Error (see dupe_gui_crash.log)")
                    self.prog.config(value=0)
                    messagebox.showerror("Error", "Crashed. Open dupe_gui_crash.log next to the script.")
        except queue.Empty:
            pass
        self.after(60, self._poll)

def main():
    try:
        app = App()
        app.mainloop()
    except Exception:
        _log("FATAL:\n" + traceback.format_exc())
        raise

if __name__ == "__main__":
    main()
