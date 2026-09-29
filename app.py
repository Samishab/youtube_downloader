#!/usr/bin/env python3
"""YouTube Downloader - تطبيق تحميل يوتيوب"""

import sys
import os
import threading
import subprocess
from pathlib import Path
from datetime import timedelta

# Auto-install dependencies
def _ensure(pkg, import_name=None):
    name = import_name or pkg
    try:
        __import__(name)
    except ImportError:
        print(f"تثبيت {pkg}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg], stdout=subprocess.DEVNULL)

_ensure("yt-dlp", "yt_dlp")
_ensure("customtkinter")

import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import tkinter as tk
import yt_dlp

# ── Theme ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

QUALITY_OPTIONS = {
    "أفضل جودة":       "bestvideo+bestaudio/best",
    "1080p":            "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p":             "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p":             "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p":             "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "صوت فقط (MP3)":   "bestaudio/best",
}

# ── Helpers ────────────────────────────────────────────────────────────────────
def fmt_size(b):
    if not b:
        return "—"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def fmt_dur(s):
    if not s:
        return "—"
    return str(timedelta(seconds=int(s)))


# ── Data model ────────────────────────────────────────────────────────────────
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

    def size_str(self):
        return fmt_size(self.filesize)

    def dur_str(self):
        return fmt_dur(self.duration)


# ── Main App ──────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Downloader ▷")
        self.geometry("1050x720")
        self.minsize(820, 580)

        self.videos: list[VideoItem] = []
        self._fetching    = False
        self._downloading = False
        self._stop_flag   = False
        self.download_dir = str(Path.home() / "Downloads")

        self._style_tree()
        self._build_ui()

    # ── Treeview style ──────────────────────────────────────────────────────
    def _style_tree(self):
        s = ttk.Style()
        s.theme_use("clam")
        bg, fg, sel = "#1e1e2e", "#cdd6f4", "#45475a"
        hbg, hfg   = "#181825", "#cdd6f4"
        s.configure("Treeview",
                     background=bg, foreground=fg,
                     fieldbackground=bg, rowheight=26,
                     font=("Segoe UI", 11))
        s.configure("Treeview.Heading",
                     background=hbg, foreground=hfg,
                     font=("Segoe UI", 11, "bold"))
        s.map("Treeview",
              background=[("selected", sel)],
              foreground=[("selected", "#cba6f7")])

    # ── UI ──────────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_top()
        self._build_list()
        self._build_bottom()

    def _build_top(self):
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        f.grid_columnconfigure(1, weight=1)

        # Row 0 – URL
        ctk.CTkLabel(f, text="الرابط:", width=90, anchor="e").grid(row=0, column=0, padx=(10, 6), pady=10)
        self.url_var = tk.StringVar()
        self.url_entry = ctk.CTkEntry(f, textvariable=self.url_var,
                                       placeholder_text="الصق رابط فيديو أو قناة يوتيوب…",
                                       height=38, font=ctk.CTkFont(size=12))
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=10)
        self.url_entry.bind("<Return>", lambda _: self._fetch())

        self.fetch_btn = ctk.CTkButton(f, text="⬇ جلب المعلومات", width=148, height=38,
                                        command=self._fetch)
        self.fetch_btn.grid(row=0, column=2, padx=(0, 10), pady=10)

        # Row 1 – Quality + folder
        ctk.CTkLabel(f, text="الجودة:", width=90, anchor="e").grid(row=1, column=0, padx=(10, 6), pady=(0, 10))
        self.quality_var = ctk.StringVar(value="أفضل جودة")
        ctk.CTkOptionMenu(f, variable=self.quality_var,
                           values=list(QUALITY_OPTIONS), width=200).grid(
            row=1, column=1, sticky="w", padx=(0, 6), pady=(0, 10))

        ctk.CTkLabel(f, text="حفظ في:", width=90, anchor="e").grid(row=2, column=0, padx=(10, 6), pady=(0, 10))
        ff = ctk.CTkFrame(f, fg_color="transparent")
        ff.grid(row=2, column=1, sticky="ew", padx=(0, 6), pady=(0, 10))
        ff.grid_columnconfigure(0, weight=1)
        self.dir_label = ctk.CTkLabel(ff, text=self.download_dir, anchor="w",
                                       fg_color=("gray80", "gray20"), corner_radius=6)
        self.dir_label.grid(row=0, column=0, sticky="ew", padx=(0, 6), ipady=4)
        ctk.CTkButton(ff, text="تغيير", width=80, command=self._pick_dir).grid(row=0, column=1)

    def _build_list(self):
        f = ctk.CTkFrame(self)
        f.grid(row=1, column=0, sticky="nsew", padx=12, pady=4)
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)

        # Header bar
        hf = ctk.CTkFrame(f, fg_color="transparent")
        hf.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))
        hf.grid_columnconfigure(0, weight=1)

        self.list_lbl = ctk.CTkLabel(hf, text="القائمة (0 فيديو)",
                                      font=ctk.CTkFont(size=13, weight="bold"))
        self.list_lbl.grid(row=0, column=0, sticky="w")

        bf = ctk.CTkFrame(hf, fg_color="transparent")
        bf.grid(row=0, column=1)
        ctk.CTkButton(bf, text="تحديد الكل",   width=100, command=lambda: self._sel_all(True)).grid(row=0, column=0, padx=2)
        ctk.CTkButton(bf, text="إلغاء التحديد", width=110, command=lambda: self._sel_all(False)).grid(row=0, column=1, padx=2)
        ctk.CTkButton(bf, text="مسح القائمة",  width=100,
                       fg_color=("gray65", "gray30"), hover_color=("gray50","gray20"),
                       command=self._clear_list).grid(row=0, column=2, padx=2)

        # Treeview
        tf = ctk.CTkFrame(f)
        tf.grid(row=1, column=0, sticky="nsew", padx=6, pady=(2, 6))
        tf.grid_columnconfigure(0, weight=1)
        tf.grid_rowconfigure(0, weight=1)

        cols = ("sel", "title", "uploader", "dur", "size", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("sel",      text="✓",       anchor="center")
        self.tree.heading("title",    text="العنوان")
        self.tree.heading("uploader", text="القناة")
        self.tree.heading("dur",      text="المدة",   anchor="center")
        self.tree.heading("size",     text="الحجم",   anchor="center")
        self.tree.heading("status",   text="الحالة",  anchor="center")

        self.tree.column("sel",      width=38,  minwidth=38,  stretch=False, anchor="center")
        self.tree.column("title",    width=420, minwidth=180)
        self.tree.column("uploader", width=150, minwidth=80)
        self.tree.column("dur",      width=75,  minwidth=55,  stretch=False, anchor="center")
        self.tree.column("size",     width=90,  minwidth=70,  stretch=False, anchor="center")
        self.tree.column("status",   width=110, minwidth=80,  stretch=False, anchor="center")

        vsb = ttk.Scrollbar(tf, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal",  command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<Button-1>", self._tree_click)
        self.tree.bind("<Double-1>", self._tree_dbl)

    def _build_bottom(self):
        f = ctk.CTkFrame(self)
        f.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 12))
        f.grid_columnconfigure(1, weight=1)

        # Buttons
        bf = ctk.CTkFrame(f, fg_color="transparent")
        bf.grid(row=0, column=0, padx=10, pady=10)

        self.dl_sel_btn = ctk.CTkButton(bf, text="⬇ تحميل المحدد",
                                         width=145, height=40,
                                         fg_color="#2d8a4e", hover_color="#246040",
                                         command=self._dl_selected)
        self.dl_sel_btn.grid(row=0, column=0, padx=(0, 5))

        self.dl_all_btn = ctk.CTkButton(bf, text="⬇ تحميل الكل",
                                         width=130, height=40,
                                         command=self._dl_all)
        self.dl_all_btn.grid(row=0, column=1, padx=5)

        self.stop_btn = ctk.CTkButton(bf, text="⏹ إيقاف",
                                       width=100, height=40,
                                       fg_color="#8b2020", hover_color="#6a1818",
                                       state="disabled", command=self._stop)
        self.stop_btn.grid(row=0, column=2, padx=(5, 0))

        # Progress
        pf = ctk.CTkFrame(f, fg_color="transparent")
        pf.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=10)
        pf.grid_columnconfigure(0, weight=1)

        self.status_lbl = ctk.CTkLabel(pf, text="جاهز", anchor="w",
                                        font=ctk.CTkFont(size=12))
        self.status_lbl.grid(row=0, column=0, sticky="ew")

        self.pbar = ctk.CTkProgressBar(pf, height=14)
        self.pbar.set(0)
        self.pbar.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # Log
        self.log = ctk.CTkTextbox(f, height=72, font=ctk.CTkFont(size=11, family="Consolas"))
        self.log.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

    # ── Actions ────────────────────────────────────────────────────────────
    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir)
        if d:
            self.download_dir = d
            self.dir_label.configure(text=d)

    def _sel_all(self, state: bool):
        for v in self.videos:
            v.selected = state
        self._redraw()

    def _clear_list(self):
        if self._downloading:
            return
        self.videos.clear()
        self.tree.delete(*self.tree.get_children())
        self.list_lbl.configure(text="القائمة (0 فيديو)")

    def _tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1":
                item = self.tree.identify_row(event.y)
                if item:
                    idx = self.tree.index(item)
                    if idx < len(self.videos):
                        self.videos[idx].selected = not self.videos[idx].selected
                        self._redraw_row(idx)

    def _tree_dbl(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            idx = self.tree.index(item)
            if idx < len(self.videos):
                v = self.videos[idx]
                import webbrowser
                webbrowser.open(v.url)

    def _redraw(self):
        for i in range(len(self.videos)):
            self._redraw_row(i)

    def _redraw_row(self, idx):
        children = self.tree.get_children()
        if idx >= len(children):
            return
        v = self.videos[idx]
        chk = "✓" if v.selected else "○"
        self.tree.item(children[idx],
                       values=(chk, v.title, v.uploader, v.dur_str(), v.size_str(), v.status))

    def _write_log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    # ── Fetch ──────────────────────────────────────────────────────────────
    def _fetch(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("تنبيه", "الرجاء إدخال رابط")
            return
        if self._fetching:
            return

        self._fetching = True
        self.fetch_btn.configure(state="disabled", text="⏳ جاري الجلب…")
        self.status_lbl.configure(text="جاري جلب معلومات الفيديو…")
        self.pbar.configure(mode="indeterminate")
        self.pbar.start()

        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url: str):
        try:
            # Step 1: fast flat extract to detect type
            flat_opts = {"quiet": True, "no_warnings": True,
                         "extract_flat": "in_playlist", "ignoreerrors": True}
            with yt_dlp.YoutubeDL(flat_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            if info is None:
                raise ValueError("لم يتمكن yt-dlp من جلب المعلومات. تحقق من الرابط.")

            entries = info.get("entries")

            if entries:
                # Playlist / channel
                entries = [e for e in entries if e]
                n = len(entries)
                self.after(0, lambda: self.status_lbl.configure(
                    text=f"جاري جلب تفاصيل {n} فيديو…"))

                videos = []
                for i, e in enumerate(entries):
                    if not self._fetching:
                        break
                    # Try to get full info for size; fall back to flat entry
                    try:
                        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                                                "ignoreerrors": True}) as ydl2:
                            full = ydl2.extract_info(
                                e.get("webpage_url") or e.get("url", ""), download=False)
                        if full:
                            videos.append(VideoItem(full))
                        else:
                            videos.append(VideoItem(e))
                    except Exception:
                        videos.append(VideoItem(e))

                    prog = (i + 1) / n
                    self.after(0, lambda p=prog, done=i+1, tot=n: [
                        self.pbar.stop(),
                        self.pbar.configure(mode="determinate"),
                        self.pbar.set(p),
                        self.status_lbl.configure(text=f"تم جلب {done}/{tot} فيديو…"),
                    ])

            else:
                # Single video – fetch full info
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                    full = ydl.extract_info(url, download=False)
                videos = [VideoItem(full)] if full else []

            self.after(0, lambda vv=videos: self._fetch_done(vv))

        except Exception as exc:
            self.after(0, lambda e=str(exc): self._fetch_error(e))

    def _fetch_done(self, videos: list):
        self._fetching = False
        self.fetch_btn.configure(state="normal", text="⬇ جلب المعلومات")
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar.set(0)

        if not videos:
            self.status_lbl.configure(text="لم يُعثر على فيديوهات")
            return

        # Append to existing list
        for v in videos:
            self.videos.append(v)
            chk = "✓"
            self.tree.insert("", "end",
                              values=(chk, v.title, v.uploader,
                                      v.dur_str(), v.size_str(), v.status))

        self.list_lbl.configure(text=f"القائمة ({len(self.videos)} فيديو)")
        self.status_lbl.configure(text=f"تم جلب {len(videos)} فيديو")
        self._write_log(f"✔ تم جلب {len(videos)} فيديو")

    def _fetch_error(self, msg: str):
        self._fetching = False
        self.fetch_btn.configure(state="normal", text="⬇ جلب المعلومات")
        self.pbar.stop()
        self.pbar.configure(mode="determinate")
        self.pbar.set(0)
        self.status_lbl.configure(text="خطأ في الجلب")
        self._write_log(f"✗ {msg}")
        messagebox.showerror("خطأ", msg)

    # ── Download ───────────────────────────────────────────────────────────
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
        self._confirm_and_start(self.videos)

    def _confirm_and_start(self, targets: list):
        known = [v.filesize for v in targets if v.filesize]
        total = sum(known)
        unk   = len(targets) - len(known)

        lines = [f"سيتم تحميل {len(targets)} فيديو.\n"]
        if total:
            lines.append(f"الحجم الإجمالي المقدَّر:  {fmt_size(total)}")
        if unk:
            lines.append(f"({unk} فيديو حجمه غير معروف)")
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

        threading.Thread(target=self._dl_worker, args=(targets,), daemon=True).start()

    def _stop(self):
        self._stop_flag = True
        self.status_lbl.configure(text="جاري الإيقاف…")

    def _dl_worker(self, targets: list):
        quality = QUALITY_OPTIONS[self.quality_var.get()]
        audio_only = "صوت" in self.quality_var.get()
        total = len(targets)

        for idx, video in enumerate(targets):
            if self._stop_flag:
                self.after(0, lambda v=video: self._set_status(v, "تم الإيقاف"))
                break

            self.after(0, lambda v=video, i=idx: [
                self.status_lbl.configure(
                    text=f"({i+1}/{total}) {v.title[:55]}…"),
                self._set_status(v, "⏳ جاري التحميل"),
            ])

            def hook(d, v=video):
                if d["status"] == "downloading":
                    pct_s = d.get("_percent_str", "").strip()
                    spd_s = d.get("_speed_str",   "").strip()
                    eta_s = d.get("_eta_str",      "").strip()
                    dl    = d.get("downloaded_bytes", 0)
                    tot   = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                    frac  = dl / tot if tot else 0
                    self.after(0, lambda ps=pct_s, ss=spd_s, es=eta_s, f=frac: [
                        self.pbar.set(f),
                        self.status_lbl.configure(
                            text=f"تحميل {ps}  |  {ss}  |  متبقي {es}"),
                    ])
                elif d["status"] == "finished":
                    self.after(0, lambda vv=v: self._set_status(vv, "✔ اكتمل"))

            pp = []
            if audio_only:
                pp.append({"key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3", "preferredquality": "192"})
            else:
                pp.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})

            opts = {
                "format":          quality,
                "outtmpl":         os.path.join(self.download_dir, "%(title)s.%(ext)s"),
                "progress_hooks":  [hook],
                "quiet":           True,
                "no_warnings":     True,
                "postprocessors":  pp,
                "ignoreerrors":    True,
                "continuedl":      True,
            }

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video.url])
                self.after(0, lambda v=video, i=idx:
                           self._write_log(f"✔ ({i+1}/{total}) {v.title}"))
            except Exception as e:
                self.after(0, lambda v=video, err=str(e): [
                    self._set_status(v, "✗ فشل"),
                    self._write_log(f"✗ {v.title}: {err}"),
                ])

            # Overall bar
            self.after(0, lambda p=(idx+1)/total: self.pbar.set(p))

        self.after(0, self._dl_done)

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

    def _dl_done(self):
        self._downloading = False
        self.dl_sel_btn.configure(state="normal")
        self.dl_all_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if not self._stop_flag:
            self.pbar.set(1)
            self.status_lbl.configure(text="✔ اكتمل التحميل")
            self._write_log("━━━ اكتمل التحميل ━━━")
        else:
            self.status_lbl.configure(text="تم الإيقاف")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
