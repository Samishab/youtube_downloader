#!/usr/bin/env python3
"""YouTube Downloader - تطبيق تحميل يوتيوب"""

import sys
import os
import threading
import ctypes
import subprocess
import webbrowser
from pathlib import Path
from datetime import timedelta

# ── Auto-install ───────────────────────────────────────────────────────────────
def _ensure(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        print(f"تثبيت {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg],
                               stdout=subprocess.DEVNULL)

_ensure("yt-dlp", "yt_dlp")
_ensure("customtkinter")

import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import tkinter as tk
import yt_dlp

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

QUALITY_OPTIONS = {
    "أفضل جودة":      "bestvideo+bestaudio/best",
    "1080p":           "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":            "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":            "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":            "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "صوت فقط (MP3)":  "bestaudio/best",
}

ARCHIVE_FILE = ".ytdl-archive.txt"   # يُحفظ في مجلد التحميل

# يمنع tkinter من عكس ترتيب الكلمات العربية (Unicode Bidi)
LRM = "‎"


# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_size(b) -> str:
    if not b:
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def fmt_dur(s) -> str:
    if not s:
        return "—"
    return str(timedelta(seconds=int(s)))

def _kill_thread(t: threading.Thread):
    """ترسل SystemExit للـ thread فوراً عبر ctypes."""
    if t and t.is_alive():
        try:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_long(t.ident),
                ctypes.py_object(SystemExit))
        except Exception:
            pass


# ── Data model ─────────────────────────────────────────────────────────────────
class VideoItem:
    def __init__(self, info: dict):
        self.id       = info.get("id", "")
        self.title    = info.get("title") or "بدون عنوان"
        self.url      = info.get("webpage_url") or info.get("url", "")
        self.duration = info.get("duration")
        self.filesize = info.get("filesize") or info.get("filesize_approx")
        self.uploader = info.get("uploader", "")
        self.selected = True
        self.status   = "انتظار"

    def size_str(self) -> str:
        return fmt_size(self.filesize)

    def dur_str(self) -> str:
        return fmt_dur(self.duration)


# ── Main App ───────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Downloader ▷")
        self.geometry("1100x740")
        self.minsize(860, 600)

        self.videos: list[VideoItem] = []
        self._fetching        = False
        self._downloading     = False
        self._stop_flag       = False
        self.download_dir     = str(Path.home() / "Downloads")

        self._fetch_thread:    threading.Thread | None = None
        self._download_thread: threading.Thread | None = None

        self._style_tree()
        self._build_ui()

    # ── Tree style ─────────────────────────────────────────────────────────────
    def _style_tree(self):
        s = ttk.Style()
        s.theme_use("clam")
        bg, fg, sel = "#1e1e2e", "#cdd6f4", "#45475a"
        s.configure("Treeview",
                     background=bg, foreground=fg, fieldbackground=bg,
                     rowheight=26, font=("Segoe UI", 11))
        s.configure("Treeview.Heading",
                     background="#181825", foreground="#cdd6f4",
                     font=("Segoe UI", 11, "bold"))
        s.map("Treeview",
              background=[("selected", sel)],
              foreground=[("selected", "#cba6f7")])

    # ── UI build ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_top()
        self._build_list()
        self._build_bottom()

    # ── Top panel (RTL: label يمين، entry وسط، زر يسار) ───────────────────────
    def _build_top(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        f.grid_columnconfigure(1, weight=1)   # عمود الـ entry يتمدد

        # صف 0 – الرابط  [زر | entry | تسمية]
        self.fetch_btn = ctk.CTkButton(
            f, text=f"{LRM}⬇ جلب المعلومات", width=150, height=38,
            command=self._fetch_or_cancel)
        self.fetch_btn.grid(row=0, column=0, padx=(10, 6), pady=10)

        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(
            f, textvariable=self.url_var,
            placeholder_text="الصق رابط فيديو أو قناة يوتيوب…",
            height=38, font=ctk.CTkFont(size=12))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=10)
        self.url_entry.bind("<Return>", lambda _: self._fetch_or_cancel())

        ctk.CTkLabel(f, text=":الرابط", width=80, anchor="e").grid(
            row=0, column=2, padx=(0, 12), pady=10)

        # صف 1 – الجودة
        self.quality_var = ctk.StringVar(value="أفضل جودة")
        ctk.CTkOptionMenu(f, variable=self.quality_var,
                           values=list(QUALITY_OPTIONS), width=200).grid(
            row=1, column=0, sticky="w", padx=(10, 6), pady=(0, 10))

        ctk.CTkLabel(f, text=":الجودة", width=80, anchor="e").grid(
            row=1, column=2, padx=(0, 12), pady=(0, 10))

        # صف 2 – مجلد الحفظ
        ff = ctk.CTkFrame(f, fg_color="transparent")
        ff.grid(row=2, column=0, columnspan=2, sticky="ew",
                padx=(10, 6), pady=(0, 10))
        ff.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(ff, text="تغيير", width=80,
                       command=self._pick_dir).grid(row=0, column=0, padx=(0, 6))
        self.dir_label = ctk.CTkLabel(
            ff, text=self.download_dir, anchor="w",
            fg_color=("gray80", "gray20"), corner_radius=6)
        self.dir_label.grid(row=0, column=1, sticky="ew", ipady=4)

        ctk.CTkLabel(f, text=":حفظ في", width=80, anchor="e").grid(
            row=2, column=2, padx=(0, 12), pady=(0, 10))

    # ── قائمة الفيديوهات ───────────────────────────────────────────────────────
    def _build_list(self):
        f = ctk.CTkFrame(self)
        f.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)

        # Header  [أزرار يسار | ملخص حجم وسط | عنوان يمين]
        hf = ctk.CTkFrame(f, fg_color="transparent")
        hf.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        hf.grid_columnconfigure(1, weight=1)

        # أزرار – col=0 (يسار)
        bf = ctk.CTkFrame(hf, fg_color="transparent")
        bf.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(bf, text=f"{LRM}مسح القائمة", width=100,
                       fg_color=("gray65", "gray30"), hover_color=("gray50", "gray20"),
                       command=self._clear_list).grid(row=0, column=0, padx=(0, 2))
        ctk.CTkButton(bf, text=f"{LRM}إلغاء التحديد", width=110,
                       command=lambda: self._sel_all(False)).grid(row=0, column=1, padx=2)
        ctk.CTkButton(bf, text=f"{LRM}تحديد الكل", width=100,
                       command=lambda: self._sel_all(True)).grid(row=0, column=2, padx=2)

        # ملخص الحجم – col=1 وسط
        self.size_lbl = ctk.CTkLabel(hf, text="",
                                      font=ctk.CTkFont(size=11),
                                      text_color=("gray40", "gray60"),
                                      anchor="center")
        self.size_lbl.grid(row=0, column=1, sticky="ew", padx=10)

        # عنوان القائمة – col=2 (يمين)
        self.list_lbl = ctk.CTkLabel(hf, text="القائمة  (0 فيديو)",
                                      font=ctk.CTkFont(size=13, weight="bold"),
                                      anchor="e")
        self.list_lbl.grid(row=0, column=2, sticky="e", padx=(0, 4))

        # Treeview
        tf = ctk.CTkFrame(f)
        tf.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        cols = ("sel", "title", "uploader", "dur", "size", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings",
                                  selectmode="browse")
        self.tree.heading("sel",      text="✓",      anchor="center")
        self.tree.heading("title",    text="العنوان", anchor="e")
        self.tree.heading("uploader", text="القناة",  anchor="e")
        self.tree.heading("dur",      text="المدة",   anchor="center")
        self.tree.heading("size",     text="الحجم",   anchor="center")
        self.tree.heading("status",   text="الحالة",  anchor="center")

        self.tree.column("sel",      width=38,  minwidth=38,  stretch=False, anchor="center")
        self.tree.column("title",    width=400, minwidth=180, anchor="e")
        self.tree.column("uploader", width=150, minwidth=80,  anchor="e")
        self.tree.column("dur",      width=75,  minwidth=55,  stretch=False, anchor="center")
        self.tree.column("size",     width=90,  minwidth=70,  stretch=False, anchor="center")
        self.tree.column("status",   width=115, minwidth=80,  stretch=False, anchor="center")

        vsb = ttk.Scrollbar(tf, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<Button-1>", self._tree_click)
        self.tree.bind("<Double-1>", self._tree_dbl)

    # ── أسفل الشاشة (RTL: progress يسار، أزرار يمين) ─────────────────────────
    def _build_bottom(self):
        f = ctk.CTkFrame(self)
        f.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 12))
        f.grid_columnconfigure(0, weight=1)   # progress يتمدد (يسار)

        # Progress – col=0 (يسار)
        pf = ctk.CTkFrame(f, fg_color="transparent")
        pf.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        pf.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(pf, text="جاهز", anchor="e",
                                        font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=0, column=0, sticky="ew")

        self.pbar = ctk.CTkProgressBar(pf, height=14)
        self.pbar.set(0)
        self.pbar.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # أزرار – col=1 (يمين)  ترتيب RTL: إيقاف | تحميل الكل | تحميل المحدد
        bf = ctk.CTkFrame(f, fg_color="transparent")
        bf.grid(row=0, column=1, padx=(0, 10), pady=10)

        self.stop_btn = ctk.CTkButton(
            bf, text=f"{LRM}⏹ إيقاف", width=100, height=40,
            fg_color="#8b2020", hover_color="#6a1818",
            state="disabled", command=self._stop)
        self.stop_btn.grid(row=0, column=0, padx=(0, 5))

        self.dl_all_btn = ctk.CTkButton(
            bf, text=f"{LRM}⬇ تحميل الكل", width=130, height=40,
            command=self._dl_all)
        self.dl_all_btn.grid(row=0, column=1, padx=5)

        self.dl_sel_btn = ctk.CTkButton(
            bf, text=f"{LRM}⬇ تحميل المحدد", width=148, height=40,
            fg_color="#2d8a4e", hover_color="#246040",
            command=self._dl_selected)
        self.dl_sel_btn.grid(row=0, column=2, padx=(5, 0))

        # لوج
        self.log_box = ctk.CTkTextbox(
            f, height=72, font=ctk.CTkFont(size=11, family="Consolas"))
        self.log_box.grid(row=1, column=0, columnspan=2, sticky="ew",
                           padx=10, pady=(0, 10))

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir)
        if d:
            self.download_dir = d
            self.dir_label.configure(text=d)

    def _sel_all(self, state: bool):
        for v in self.videos:
            v.selected = state
        self._redraw()
        self._update_size_summary()

    def _clear_list(self):
        if self._downloading:
            return
        self.videos.clear()
        self.tree.delete(*self.tree.get_children())
        self.list_lbl.configure(text="القائمة  (0 فيديو)")
        self.size_lbl.configure(text="")

    def _tree_click(self, event):
        if (self.tree.identify_region(event.x, event.y) == "cell"
                and self.tree.identify_column(event.x) == "#1"):
            item = self.tree.identify_row(event.y)
            if item:
                idx = self.tree.index(item)
                if idx < len(self.videos):
                    self.videos[idx].selected = not self.videos[idx].selected
                    self._redraw_row(idx)
                    self._update_size_summary()

    def _tree_dbl(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            idx = self.tree.index(item)
            if idx < len(self.videos):
                webbrowser.open(self.videos[idx].url)

    def _redraw(self):
        for i in range(len(self.videos)):
            self._redraw_row(i)

    def _redraw_row(self, idx: int):
        children = self.tree.get_children()
        if idx >= len(children):
            return
        v = self.videos[idx]
        chk = "✓" if v.selected else "○"
        self.tree.item(children[idx],
                       values=(chk, v.title, v.uploader,
                                v.dur_str(), v.size_str(), v.status))

    def _update_size_summary(self):
        sel   = [v for v in self.videos if v.selected]
        known = [v.filesize for v in sel if v.filesize]
        total = sum(known)
        unk   = len(sel) - len(known)
        parts = [f"محدد: {len(sel)}/{len(self.videos)}"]
        if total:
            parts.append(fmt_size(total))
        if unk:
            parts.append(f"+ {unk} مجهول الحجم")
        self.size_lbl.configure(text="  |  ".join(parts))

    def _set_status(self, video: VideoItem, status: str):
        video.status = status
        children = self.tree.get_children()
        try:
            idx = self.videos.index(video)
            if idx < len(children):
                vals = list(self.tree.item(children[idx], "values"))
                vals[5] = status
                self.tree.item(children[idx], values=vals)
        except (ValueError, IndexError):
            pass

    def _write_log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    # ── Fetch ──────────────────────────────────────────────────────────────────
    def _fetch_or_cancel(self):
        if self._fetching:
            # إيقاف الجلب
            self._fetching = False
            _kill_thread(self._fetch_thread)
            self.fetch_btn.configure(text=f"{LRM}⬇ جلب المعلومات",
                                      fg_color=["#1f538d", "#1f538d"])
            self.pbar.stop()
            self.pbar.configure(mode="determinate")
            self.pbar.set(0)
            self.status_lbl.configure(text="تم إيقاف الجلب")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("تنبيه", "الرجاء إدخال رابط")
            return

        self._fetching = True
        self.fetch_btn.configure(text=f"{LRM}⏹ إيقاف الجلب",
                                  fg_color=["#8b2020", "#8b2020"])
        self.status_lbl.configure(text="جاري جلب المعلومات…")
        self.pbar.configure(mode="indeterminate")
        self.pbar.start()

        self._fetch_thread = threading.Thread(
            target=self._fetch_worker, args=(url,), daemon=True)
        self._fetch_thread.start()

    def _fetch_worker(self, url: str):
        try:
            flat_opts = {"quiet": True, "no_warnings": True,
                         "extract_flat": "in_playlist", "ignoreerrors": True,
                         "socket_timeout": 15}
            with yt_dlp.YoutubeDL(flat_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if info is None:
                raise ValueError("لم يتمكن من جلب المعلومات — تحقق من الرابط")

            entries = info.get("entries")

            if entries:
                entries = [e for e in entries if e]
                n = len(entries)
                self.after(0, lambda: [
                    self.pbar.stop(),
                    self.pbar.configure(mode="determinate"),
                    self.pbar.set(0),
                    self.status_lbl.configure(text=f"جاري جلب تفاصيل {n} فيديو…"),
                ])

                videos: list[VideoItem] = []
                running_size = 0

                for i, e in enumerate(entries):
                    if not self._fetching:
                        break
                    try:
                        with yt_dlp.YoutubeDL(
                                {"quiet": True, "no_warnings": True,
                                 "ignoreerrors": True, "socket_timeout": 15}) as ydl2:
                            full = ydl2.extract_info(
                                e.get("webpage_url") or e.get("url", ""),
                                download=False)
                        item = VideoItem(full if full else e)
                    except Exception:
                        item = VideoItem(e)

                    videos.append(item)
                    if item.filesize:
                        running_size += item.filesize

                    prog = (i + 1) / n
                    size_txt = f" — {fmt_size(running_size)}" if running_size else ""
                    self.after(0, lambda p=prog, d=i+1, t=n, s=size_txt: [
                        self.pbar.set(p),
                        self.status_lbl.configure(
                            text=f"جلب {d}/{t} فيديو{s}"),
                    ])
            else:
                with yt_dlp.YoutubeDL(
                        {"quiet": True, "no_warnings": True,
                         "socket_timeout": 15}) as ydl:
                    full = ydl.extract_info(url, download=False)
                videos = [VideoItem(full)] if full else []

            self.after(0, lambda vv=videos: self._fetch_done(vv))

        except SystemExit:
            pass
        except Exception as exc:
            self.after(0, lambda e=str(exc): self._fetch_error(e))

    def _fetch_done(self, videos: list):
        self._fetching = False
        self.fetch_btn.configure(text=f"{LRM}⬇ جلب المعلومات",
                                  fg_color=["#1f538d", "#1f538d"])
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar.set(0)

        if not videos:
            self.status_lbl.configure(text="لم يُعثر على فيديوهات")
            return

        for v in videos:
            self.videos.append(v)
            self.tree.insert("", "end",
                              values=("✓", v.title, v.uploader,
                                      v.dur_str(), v.size_str(), v.status))

        self.list_lbl.configure(text=f"القائمة  ({len(self.videos)} فيديو)")
        self._update_size_summary()

        known = [v.filesize for v in videos if v.filesize]
        total = sum(known)
        unk   = len(videos) - len(known)
        parts = [f"✔ تم جلب {len(videos)} فيديو"]
        if total:
            parts.append(fmt_size(total))
        if unk:
            parts.append(f"{unk} مجهول")
        msg = "  |  ".join(parts)
        self.status_lbl.configure(text=msg)
        self._write_log(msg)

    def _fetch_error(self, msg: str):
        self._fetching = False
        self.fetch_btn.configure(text=f"{LRM}⬇ جلب المعلومات",
                                  fg_color=["#1f538d", "#1f538d"])
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar.set(0)
        self.status_lbl.configure(text="خطأ في الجلب")
        self._write_log(f"✗ {msg}")
        messagebox.showerror("خطأ", msg)

    # ── Download ───────────────────────────────────────────────────────────────
    def _dl_selected(self):
        targets = [v for v in self.videos if v.selected]
        if not targets:
            messagebox.showwarning("تنبيه", "لم تحدد أي فيديو للتحميل")
            return
        self._confirm_and_start(targets)

    def _dl_all(self):
        if not self.videos:
            messagebox.showwarning("تنبيه", "القائمة فارغة")
            return
        self._confirm_and_start(self.videos[:])

    def _confirm_and_start(self, targets: list):
        known = [v.filesize for v in targets if v.filesize]
        total = sum(known)
        unk   = len(targets) - len(known)

        # كم فيديو محمّل مسبقاً في الأرشيف
        archive = os.path.join(self.download_dir, ARCHIVE_FILE)
        skippable = 0
        if os.path.exists(archive):
            with open(archive, encoding="utf-8") as af:
                done_ids = {ln.strip().split()[-1]
                            for ln in af if ln.strip()}
            skippable = sum(1 for v in targets if v.id in done_ids)

        lines = [f"سيتم تحميل {len(targets)} فيديو.\n"]
        if total:
            lines.append(f"الحجم الإجمالي المقدَّر:  {fmt_size(total)}")
        if unk:
            lines.append(f"({unk} فيديو حجمه غير معروف)")
        if skippable:
            lines.append(f"\n⏭ {skippable} فيديو سيُتجاوز (محمّل مسبقاً)")
        lines += [f"\nالجودة:  {self.quality_var.get()}",
                  f"الحفظ في:  {self.download_dir}\n",
                  "هل تريد المتابعة؟"]

        if messagebox.askyesno("تأكيد التحميل", "\n".join(lines)):
            self._start_dl(targets)

    def _start_dl(self, targets: list):
        for v in targets:
            v.status = "في الانتظار"
        self._redraw()

        self._downloading = True
        self._stop_flag   = False
        self.dl_sel_btn.configure(state="disabled")
        self.dl_all_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.pbar.set(0)

        self._download_thread = threading.Thread(
            target=self._dl_worker, args=(targets,), daemon=True)
        self._download_thread.start()

    def _stop(self):
        """إيقاف فوري: يُرسل SystemExit للـ thread الحالي."""
        self._stop_flag = True
        self.status_lbl.configure(text="⏹ جاري الإيقاف…")
        _kill_thread(self._download_thread)

    def _dl_worker(self, targets: list):
        quality    = QUALITY_OPTIONS[self.quality_var.get()]
        audio_only = "صوت" in self.quality_var.get()
        total      = len(targets)
        archive    = os.path.join(self.download_dir, ARCHIVE_FILE)
        completed  = 0

        pp = ([{"key": "FFmpegExtractAudio",
                "preferredcodec": "mp3", "preferredquality": "192"}]
              if audio_only
              else [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}])

        try:
            for idx, video in enumerate(targets):
                if self._stop_flag:
                    self.after(0, lambda v=video: self._set_status(v, "⏹ توقف"))
                    break

                self.after(0, lambda v=video, i=idx: [
                    self.status_lbl.configure(
                        text=f"({i+1}/{total})  {v.title[:52]}…"),
                    self._set_status(v, "⏳ جاري التحميل"),
                ])

                def hook(d, v=video):
                    if self._stop_flag:
                        return
                    if d["status"] == "downloading":
                        pct = d.get("_percent_str", "").strip()
                        spd = d.get("_speed_str",   "").strip()
                        eta = d.get("_eta_str",      "").strip()
                        dl  = d.get("downloaded_bytes", 0)
                        tot = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                        frac = dl / tot if tot else 0
                        self.after(0, lambda pc=pct, sp=spd, et=eta, f=frac: [
                            self.pbar.set(f),
                            self.status_lbl.configure(
                                text=f"{pc}  ·  {sp}  ·  متبقي {et}"),
                        ])
                    elif d["status"] == "finished":
                        self.after(0, lambda: self.status_lbl.configure(
                            text="⚙ جاري المعالجة…"))

                opts = {
                    "format":           quality,
                    "outtmpl":          os.path.join(self.download_dir,
                                                      "%(title)s.%(ext)s"),
                    "progress_hooks":   [hook],
                    "quiet":            True,
                    "no_warnings":      True,
                    "postprocessors":   pp,
                    "ignoreerrors":     True,
                    "continuedl":       True,
                    "download_archive": archive,   # تخطي المحمّل مسبقاً
                    "nooverwrites":     True,       # تخطي الملفات الموجودة
                }

                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ret = ydl.download([video.url])

                    if ret == 0:
                        completed += 1
                        self.after(0, lambda v=video, i=idx: [
                            self._set_status(v, "✔ اكتمل"),
                            self._write_log(f"✔ ({i+1}/{total})  {v.title}"),
                        ])
                    else:
                        # yt-dlp أعاد != 0 يعني تخطّاه (في الأرشيف أو موجود)
                        self.after(0, lambda v=video, i=idx: [
                            self._set_status(v, "⏭ موجود مسبقاً"),
                            self._write_log(f"⏭ ({i+1}/{total})  {v.title}  — تم التخطي"),
                        ])

                except SystemExit:
                    self.after(0, lambda v=video: self._set_status(v, "⏹ توقف"))
                    break
                except Exception as e:
                    self.after(0, lambda v=video, err=str(e): [
                        self._set_status(v, "✗ فشل"),
                        self._write_log(f"✗  {video.title}: {err}"),
                    ])

                # شريط التقدم الكلي حسب عدد الفيديوهات
                self.after(0, lambda p=(idx + 1) / total: self.pbar.set(p))

        except SystemExit:
            pass

        self.after(0, lambda c=completed, t=total: self._dl_done(c, t))

    def _dl_done(self, completed: int, total: int):
        self._downloading = False
        self.dl_sel_btn.configure(state="normal")
        self.dl_all_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

        if not self._stop_flag:
            self.pbar.set(1)
            msg = f"✔ اكتمل  —  {completed}/{total} فيديو"
            self.status_lbl.configure(text=msg)
            self._write_log(f"━━━  {msg}  ━━━")
        else:
            self.status_lbl.configure(text="⏹ تم الإيقاف")
            self._write_log("━━━  تم إيقاف التحميل  ━━━")


# ── Entry ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().mainloop()
