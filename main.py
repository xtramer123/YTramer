from __future__ import annotations

import queue
import shutil
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import tkinter as tk

APP_NAME = "YTramer"

AUDIO_FORMATS: dict[str, str] = {
    "MP3": "mp3",
    "WAV": "wav",
    "M4A": "m4a",
    "OPUS": "opus",
    "FLAC": "flac",
}

VIDEO_FORMATS: dict[str, str] = {
    "MP4": "mp4",
    "WEBM": "webm",
}

QUALITIES: dict[str, str] = {
    "Mejor calidad": "0",
    "Alta": "192",
    "Media": "128",
    "Baja": "96",
}

LOSSLESS = {"wav", "flac"}


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def find_ffmpeg() -> str | None:
    root = base_dir()
    for candidate in (root / "ffmpeg.exe", root / "bin" / "ffmpeg.exe"):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def find_deno() -> str | None:
    root = base_dir()
    for candidate in (root / "deno.exe", root / "bin" / "deno.exe"):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("deno")


def default_output() -> Path:
    downloads = Path.home() / "Downloads"
    root = downloads if downloads.is_dir() else Path.home()
    return root / APP_NAME


def load_ytdlp():
    try:
        import yt_dlp
    except ImportError:
        return None
    return yt_dlp


class Downloader:
    def __init__(self, url: str, folder: Path, fmt: str, quality: str) -> None:
        self.url = url
        self.folder = folder
        self.fmt = fmt
        self.quality = quality

    def options(self) -> dict:
        opts: dict = {
            "outtmpl": str(self.folder / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "noprogress": True,
            "consoletitle": False,
            "overwrites": False,
            "windowsfilenames": True,
            "ignoreerrors": False,
            "retries": 5,
            "fragment_retries": 5,
        }

        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg

        deno = find_deno()
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
            opts["remote_components"] = ["ejs:github"]

        if self.fmt in VIDEO_FORMATS.values():
            opts["format"] = "bestvideo+bestaudio/best"
            opts["merge_output_format"] = self.fmt
            return opts

        opts["format"] = "bestaudio/best"
        audio: dict = {"preferredcodec": self.fmt}
        if self.fmt not in LOSSLESS:
            audio["preferredquality"] = self.quality
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", **audio}]
        return opts


class App:
    MSG_DOWNLOADING = "downloading"
    MSG_DONE = "done"
    MSG_ERROR = "error"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[object] = queue.Queue()
        self.worker: threading.Thread | None = None

        self.url_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(default_output()))
        self.format_var = tk.StringVar(value="MP3")
        self.quality_var = tk.StringVar(value="Mejor calidad")
        self.status_var = tk.StringVar(value="Listo")

        self._build_ui()
        self._update_quality_state()

    def _build_ui(self) -> None:
        root = self.root
        root.title(APP_NAME)
        root.resizable(False, False)

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")

        frame = ttk.Frame(root, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        GAP = {"pady": 7}

        ttk.Label(frame, text="YTramer", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            frame, text="Descarga video o audio de YouTube", font=("Segoe UI", 9)
        ).grid(row=1, column=0, columnspan=3, sticky="w")

        ttk.Separator(frame).grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 8))

        ttk.Label(frame, text="Link").grid(row=3, column=0, sticky="w", **GAP)
        self.url_entry = ttk.Entry(frame, textvariable=self.url_var, width=46)
        self.url_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=(10, 0), **GAP)
        self.url_entry.bind("<Return>", lambda _e: self._start())
        self.root.after(100, self._focus_url)

        ttk.Label(frame, text="Guardar en").grid(row=4, column=0, sticky="w", **GAP)
        ttk.Entry(frame, textvariable=self.folder_var, width=46).grid(
            row=4, column=1, sticky="ew", padx=(10, 6), **GAP
        )
        ttk.Button(frame, text="Carpeta", command=self._pick_folder).grid(row=4, column=2, **GAP)

        ttk.Label(frame, text="Formato").grid(row=5, column=0, sticky="w", **GAP)
        self.format_box = ttk.Combobox(
            frame,
            textvariable=self.format_var,
            values=[*AUDIO_FORMATS, *VIDEO_FORMATS],
            state="readonly",
            width=12,
        )
        self.format_box.grid(row=5, column=1, sticky="w", padx=(10, 0), **GAP)
        self.format_box.bind("<<ComboboxSelected>>", lambda _e: self._update_quality_state())

        ttk.Label(frame, text="Calidad").grid(row=6, column=0, sticky="w", **GAP)
        self.quality_box = ttk.Combobox(
            frame,
            textvariable=self.quality_var,
            values=list(QUALITIES),
            state="readonly",
            width=12,
        )
        self.quality_box.grid(row=6, column=1, sticky="w", padx=(10, 0), **GAP)

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 2))

        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 9)).grid(
            row=8, column=0, columnspan=3, sticky="w"
        )

        self.button = ttk.Button(frame, text="Descargar", command=self._start)
        self.button.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        frame.columnconfigure(1, weight=1)

    def _focus_url(self) -> None:
        self.url_entry.focus_set()

    def _pick_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.folder_var.get())
        if chosen:
            self.folder_var.set(chosen)

    def _update_quality_state(self) -> None:
        lossless = self.format_var.get() in ("WAV", "FLAC")
        self.quality_box.configure(state="disabled" if lossless else "readonly")

    def _reset(self) -> None:
        self.progress["value"] = 0
        self.button.configure(state="normal")
        self.url_entry.configure(state="normal")
        self.format_box.configure(state="readonly")
        self._update_quality_state()

    def _lock(self) -> None:
        self.button.configure(state="disabled")
        self.url_entry.configure(state="disabled")
        self.format_box.configure(state="disabled")

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        url = self.url_var.get().strip()
        if not url:
            self.status_var.set("Pega un link de YouTube")
            self.url_entry.focus_set()
            return
        if "youtube.com" not in url and "youtu.be" not in url:
            messagebox.showwarning(APP_NAME, "El link no parece ser de YouTube.")
            return

        if load_ytdlp() is None:
            messagebox.showerror(
                APP_NAME, "Falta la libreria yt-dlp.\nInstala con:  pip install -U yt-dlp"
            )
            return
        if find_ffmpeg() is None:
            messagebox.showerror(
                APP_NAME, "No se encontro ffmpeg, necesario para convertir el audio."
            )
            return

        folder = Path(self.folder_var.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"No se pudo crear la carpeta:\n{exc}")
            return

        fmt = (AUDIO_FORMATS | VIDEO_FORMATS)[self.format_var.get()]
        job = Downloader(url, folder, fmt, QUALITIES[self.quality_var.get()])

        self._lock()
        self.progress["value"] = 0
        self.status_var.set("Preparando...")
        self.events = queue.Queue()
        self.worker = threading.Thread(target=self._run, args=(job,), daemon=True)
        self.worker.start()

    def _run(self, job: Downloader) -> None:
        yt_dlp = load_ytdlp()

        def hook(data: dict) -> None:
            self.events.put((App.MSG_DOWNLOADING, data))

        opts = job.options()
        opts["progress_hooks"] = [hook]
        opts["postprocessor_hooks"] = [hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
            self.events.put((App.MSG_DONE, info))
        except Exception as exc:
            self.events.put((App.MSG_ERROR, exc))

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == App.MSG_DOWNLOADING:
                    self._on_progress(payload)
                elif kind == App.MSG_DONE:
                    self._on_done(payload)
                else:
                    self._on_error(payload)
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _on_progress(self, data: dict) -> None:
        status = data.get("status")

        if status == "processing":
            self.status_var.set("Convirtiendo a audio...")
            return

        if status == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            if total:
                self.progress["value"] = min(done / total * 100, 100)
            speed = data.get("speed")
            eta = data.get("eta")
            parts = [f"{self.progress['value']:.0f}%"]
            if speed:
                parts.append(f"{speed / 1_048_576:.1f} MB/s")
            if eta:
                parts.append(f"{eta // 60}:{eta % 60:02d} restante")
            self.status_var.set(" | ".join(parts))
            return

        if status == "finished":
            self.status_var.set("Procesando archivo...")
            self.progress["value"] = 100

    def _on_done(self, info: dict) -> None:
        self._reset()
        name = info.get("title") or "archivo"
        self.status_var.set(f"Listo: {name}")
        messagebox.showinfo(APP_NAME, f"Descarga completada:\n\n{name}")

    def _on_error(self, exc: Exception) -> None:
        self._reset()
        self.status_var.set("Error en la descarga")
        messagebox.showerror(APP_NAME, f"No se pudo descargar:\n\n{exc}")

    def run(self) -> None:
        self.root.after(120, self._poll)
        self.root.mainloop()


def main() -> None:
    App(tk.Tk()).run()


if __name__ == "__main__":
    main()