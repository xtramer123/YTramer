from __future__ import annotations

import os
import queue
import shutil
import subprocess
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

INVALID_CHARS = '<>:"/\\|?*'
MAX_NAME_LENGTH = 120
MIN_SECTION = 1.0
NUDGE = 5.0


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


def expose_ffmpeg() -> None:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return
    folder = str(Path(ffmpeg).resolve().parent).lower()
    current = os.environ.get("PATH", "")
    if folder not in [entry.lower() for entry in current.split(os.pathsep) if entry]:
        os.environ["PATH"] = os.pathsep.join([folder, current]) if current else folder


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


def sanitize_name(raw: str) -> str:
    cleaned = "".join(
        "_" if (ch in INVALID_CHARS or not ch.isprintable()) else ch for ch in raw
    )
    return cleaned.strip().rstrip(". ")[:MAX_NAME_LENGTH]


def unique_stem(folder: Path, name: str) -> str:
    taken = {os.path.splitext(entry.name)[0].lower() for entry in os.scandir(folder)}
    candidate = name
    index = 2
    while candidate.lower() in taken:
        candidate = f"{name} ({index})"
        index += 1
    return candidate


def format_time(seconds: float) -> str:
    total = max(int(round(seconds)), 0)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def parse_time(text: str) -> float | None:
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None
    try:
        values = [float(part) for part in parts]
    except ValueError:
        return None
    seconds = 0.0
    for value in values:
        seconds = seconds * 60 + value
    return seconds if seconds >= 0 else None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def trim_file(source: Path, target: Path, start: float, end: float, fmt: str) -> None:
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg no esta disponible.")
    args = [
        exe, "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(source),
        "-t", f"{max(end - start, MIN_SECTION):.3f}",
    ]
    if fmt in AUDIO_FORMATS.values():
        args += ["-vn", "-c:a", "copy"]
    else:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    args.append(str(target))
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffmpeg no pudo recortar el archivo.")


class Downloader:
    def __init__(
        self,
        url: str,
        folder: Path,
        fmt: str,
        quality: str,
        stem: str = "",
        section: tuple[float, float] | None = None,
    ) -> None:
        self.url = url
        self.folder = folder
        self.fmt = fmt
        self.quality = quality
        self.stem = stem
        self.section = section

    def options(self) -> dict:
        template = f"{self.stem}.%(ext)s" if self.stem else "%(title)s.%(ext)s"
        opts: dict = {
            "outtmpl": str(self.folder / template),
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

    def section_options(self) -> dict:
        start, end = self.section
        return {
            "download_ranges": lambda _info, _ydl: [{"start_time": start, "end_time": end}],
            "force_keyframes_at_cuts": True,
            "external_downloader": {"default": "ffmpeg"},
            "external_downloader_args": {"ffmpeg": ["-nostdin", "-loglevel", "error"]},
        }


class TrimDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        video_title: str,
        duration: float,
        initial: tuple[float, float] | None,
        on_apply,
    ) -> None:
        super().__init__(parent)
        self.duration = duration
        self.on_apply = on_apply
        self._syncing = False

        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.length_var = tk.StringVar()

        self.title("Recortar")
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

        frame = ttk.Frame(self, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        GAP = {"pady": 6}

        ttk.Label(frame, text="Recortar", font=("Segoe UI", 13, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w"
        )
        ttk.Label(frame, text=video_title, wraplength=420).grid(
            row=1, column=0, columnspan=5, sticky="w", pady=(2, 0)
        )
        ttk.Label(frame, text=f"Duracion total: {format_time(duration)}").grid(
            row=2, column=0, columnspan=5, sticky="w", **GAP
        )
        ttk.Separator(frame).grid(row=3, column=0, columnspan=5, sticky="ew", pady=(4, 8))

        self.start_scale = self._slider(frame, 4, "Desde", self.start_var)
        self.end_scale = self._slider(frame, 5, "Hasta", self.end_var)

        ttk.Label(frame, textvariable=self.length_var).grid(
            row=6, column=0, columnspan=5, sticky="w", **GAP
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=5, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Todo el audio", command=self._whole).pack(side="left")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Aplicar y descargar", command=self._apply).pack(
            side="right", padx=(0, 8)
        )

        frame.columnconfigure(1, weight=1)

        start, end = initial or (0.0, duration)
        self._set_values(start, end)
        self.grab_set()
        self.focus_set()

    def _slider(self, frame: ttk.Frame, row: int, label: str, var: tk.StringVar) -> ttk.Scale:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=6)
        scale = ttk.Scale(frame, from_=0.0, to=self.duration, orient="horizontal")
        scale.grid(row=row, column=1, sticky="ew", pady=6)
        entry = ttk.Entry(frame, textvariable=var, width=8)
        entry.grid(row=row, column=2, sticky="w", padx=8)
        entry.bind("<Return>", lambda _e: self._from_entry(scale, var))
        entry.bind("<FocusOut>", lambda _e: self._from_entry(scale, var))
        ttk.Button(frame, text="-5s", width=4, command=lambda: self._nudge(scale, -NUDGE)).grid(
            row=row, column=3, padx=(0, 4), pady=6
        )
        ttk.Button(frame, text="+5s", width=4, command=lambda: self._nudge(scale, NUDGE)).grid(
            row=row, column=4, pady=6
        )
        scale.configure(command=lambda _v: self._from_scale(scale))
        return scale

    def _from_scale(self, scale: ttk.Scale) -> None:
        if self._syncing:
            return
        value = round(scale.get(), 1)
        start, end = self._values()
        if scale is self.start_scale:
            start = min(value, max(self.duration - MIN_SECTION, 0.0))
            end = end if end - start >= MIN_SECTION else min(start + MIN_SECTION, self.duration)
        else:
            end = max(value, MIN_SECTION)
            start = start if end - start >= MIN_SECTION else max(end - MIN_SECTION, 0.0)
        self._set_values(start, end)

    def _from_entry(self, scale: ttk.Scale, var: tk.StringVar) -> None:
        parsed = parse_time(var.get())
        if parsed is None:
            var.set(format_time(scale.get()))
            return
        start, end = self._values()
        if scale is self.start_scale:
            self._set_values(min(parsed, end - MIN_SECTION), end)
        else:
            self._set_values(start, max(parsed, start + MIN_SECTION))

    def _nudge(self, scale: ttk.Scale, delta: float) -> None:
        start, end = self._values()
        if scale is self.start_scale:
            self._set_values(scale.get() + delta, end)
        else:
            self._set_values(start, scale.get() + delta)

    def _whole(self) -> None:
        self._set_values(0.0, self.duration)

    def _values(self) -> tuple[float, float]:
        return round(self.start_scale.get(), 1), round(self.end_scale.get(), 1)

    def _set_values(self, start: float, end: float) -> None:
        start = round(clamp(start, 0.0, self.duration), 1)
        end = round(clamp(end, 0.0, self.duration), 1)
        if end - start < MIN_SECTION:
            end = round(min(start + MIN_SECTION, self.duration), 1)
        self._syncing = True
        try:
            if abs(self.start_scale.get() - start) > 0.05:
                self.start_scale.set(start)
            if abs(self.end_scale.get() - end) > 0.05:
                self.end_scale.set(end)
        finally:
            self._syncing = False
        self.start_var.set(format_time(start))
        self.end_var.set(format_time(end))
        self.length_var.set(
            f"Recorte: {format_time(end - start)}  "
            f"({format_time(start)} a {format_time(end)})"
        )

    def _apply(self) -> None:
        start, end = self._values()
        if end - start < MIN_SECTION - 0.05:
            messagebox.showwarning(
                APP_NAME, "El recorte debe durar al menos 1 segundo.", parent=self
            )
            return
        self.on_apply(start, end)
        self.destroy()


class App:
    MSG_DOWNLOADING = "downloading"
    MSG_STATUS = "status"
    MSG_DONE = "done"
    MSG_ERROR = "error"
    MSG_META = "meta"
    MSG_META_ERROR = "meta_error"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.meta: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.probing: threading.Thread | None = None
        self.job: Downloader | None = None
        self.trim: tuple[float, float] | None = None
        self.trim_url: str = ""

        self.url_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.folder_var = tk.StringVar(value=str(default_output()))
        self.format_var = tk.StringVar(value="MP3")
        self.quality_var = tk.StringVar(value="Mejor calidad")
        self.status_var = tk.StringVar(value="Listo")
        self.trim_var = tk.StringVar(value="Recorte: desactivado")

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
        self.url_entry = ttk.Entry(frame, textvariable=self.url_var, width=40)
        self.url_entry.grid(row=3, column=1, sticky="ew", padx=(10, 6), **GAP)
        self.url_entry.bind("<Return>", lambda _e: self._start())
        self.url_entry.bind("<<Modified>>", self._on_url_modified)
        self.trim_button = ttk.Button(frame, text="Recortar", command=self._open_trim)
        self.trim_button.grid(row=3, column=2, **GAP)
        self.root.after(100, self._focus_url)

        ttk.Label(frame, text="Nombre (opcional)").grid(row=4, column=0, sticky="w", **GAP)
        self.name_entry = ttk.Entry(frame, textvariable=self.name_var, width=40)
        self.name_entry.grid(row=4, column=1, columnspan=2, sticky="ew", padx=(10, 0), **GAP)
        self.name_entry.bind("<Return>", lambda _e: self._start())

        ttk.Label(frame, text="Guardar en").grid(row=5, column=0, sticky="w", **GAP)
        ttk.Entry(frame, textvariable=self.folder_var, width=46).grid(
            row=5, column=1, sticky="ew", padx=(10, 6), **GAP
        )
        ttk.Button(frame, text="Carpeta", command=self._pick_folder).grid(row=5, column=2, **GAP)

        ttk.Label(frame, text="Formato").grid(row=6, column=0, sticky="w", **GAP)
        self.format_box = ttk.Combobox(
            frame,
            textvariable=self.format_var,
            values=[*AUDIO_FORMATS, *VIDEO_FORMATS],
            state="readonly",
            width=12,
        )
        self.format_box.grid(row=6, column=1, sticky="w", padx=(10, 0), **GAP)
        self.format_box.bind("<<ComboboxSelected>>", lambda _e: self._update_quality_state())

        ttk.Label(frame, text="Calidad").grid(row=7, column=0, sticky="w", **GAP)
        self.quality_box = ttk.Combobox(
            frame,
            textvariable=self.quality_var,
            values=list(QUALITIES),
            state="readonly",
            width=12,
        )
        self.quality_box.grid(row=7, column=1, sticky="w", padx=(10, 0), **GAP)

        ttk.Label(frame, textvariable=self.trim_var, font=("Segoe UI", 9)).grid(
            row=8, column=0, columnspan=2, sticky="w", **GAP
        )
        self.clear_trim_button = ttk.Button(
            frame, text="Quitar", command=lambda: self._set_trim(None), state="disabled"
        )
        self.clear_trim_button.grid(row=8, column=2, **GAP)

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(6, 2))

        ttk.Label(frame, textvariable=self.status_var, font=("Segoe UI", 9)).grid(
            row=10, column=0, columnspan=3, sticky="w"
        )

        self.button = ttk.Button(frame, text="Descargar", command=self._start)
        self.button.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(10, 0))

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

    def _set_trim(self, section: tuple[float, float] | None) -> None:
        self.trim = section
        if section:
            self.trim_url = self.url_var.get().strip()
            start, end = section
            self.trim_var.set(
                f"Recorte: {format_time(end - start)}  "
                f"({format_time(start)} a {format_time(end)})"
            )
            self.clear_trim_button.configure(state="normal")
        else:
            self.trim_url = ""
            self.trim_var.set("Recorte: desactivado")
            self.clear_trim_button.configure(state="disabled")

    def _on_url_modified(self) -> None:
        if self.url_entry.edit_modified():
            self.url_entry.edit_modified(False)
            if self.trim:
                self._set_trim(None)

    def _set_probe_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.url_entry.configure(state=state)
        self.trim_button.configure(state=state)
        self.status_var.set("Obteniendo duracion..." if busy else "Listo")

    def _reset(self) -> None:
        self.progress["value"] = 0
        self.button.configure(state="normal")
        self.url_entry.configure(state="normal")
        self.name_entry.configure(state="normal")
        self.format_box.configure(state="readonly")
        self.trim_button.configure(state="normal")
        self._update_quality_state()

    def _lock(self) -> None:
        self.button.configure(state="disabled")
        self.url_entry.configure(state="disabled")
        self.name_entry.configure(state="disabled")
        self.format_box.configure(state="disabled")
        self.trim_button.configure(state="disabled")
        self.clear_trim_button.configure(state="disabled")

    def _check_url(self) -> str | None:
        url = self.url_var.get().strip()
        if not url:
            self.status_var.set("Pega un link de YouTube")
            self.url_entry.focus_set()
            return None
        if "youtube.com" not in url and "youtu.be" not in url:
            messagebox.showwarning(APP_NAME, "El link no parece ser de YouTube.")
            return None
        return url

    def _check_engine(self) -> bool:
        if load_ytdlp() is None:
            messagebox.showerror(
                APP_NAME, "Falta la libreria yt-dlp.\nInstala con:  pip install -U yt-dlp"
            )
            return False
        if find_ffmpeg() is None:
            messagebox.showerror(
                APP_NAME, "No se encontro ffmpeg, necesario para convertir el audio."
            )
            return False
        return True

    def _open_trim(self) -> None:
        if (self.worker and self.worker.is_alive()) or (
            self.probing and self.probing.is_alive()
        ):
            return
        url = self._check_url()
        if not url or not self._check_engine():
            return

        self.meta = queue.Queue()
        self._set_probe_busy(True)
        self.probing = threading.Thread(target=self._probe, args=(url,), daemon=True)
        self.probing.start()

    def _probe(self, url: str) -> None:
        yt_dlp = load_ytdlp()
        opts: dict = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}

        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = ffmpeg

        deno = find_deno()
        if deno:
            opts["js_runtimes"] = {"deno": {"path": deno}}
            opts["remote_components"] = ["ejs:github"]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.meta.put((App.MSG_META, info))
        except Exception as exc:
            self.meta.put((App.MSG_META_ERROR, exc))

    def _on_meta(self, info: dict) -> None:
        self._set_probe_busy(False)
        duration = float(info.get("duration") or 0)
        if duration <= 0:
            messagebox.showwarning(
                APP_NAME, "No se pudo obtener la duracion del video.\nNo se puede recortar."
            )
            return
        TrimDialog(self.root, info.get("title") or "Video", duration, self.trim, self._apply_trim)

    def _on_meta_error(self, exc: Exception) -> None:
        self._set_probe_busy(False)
        messagebox.showerror(APP_NAME, f"No se pudo leer el video:\n\n{exc}")

    def _apply_trim(self, start: float, end: float) -> None:
        self._set_trim((start, end))
        self.root.after_idle(self._start)

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        url = self._check_url()
        if not url or not self._check_engine():
            return

        if self.trim and url != self.trim_url:
            self._set_trim(None)

        folder = Path(self.folder_var.get()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"No se pudo crear la carpeta:\n{exc}")
            return

        name = sanitize_name(self.name_var.get())
        if name != self.name_var.get().strip():
            self.name_var.set(name)

        fmt = (AUDIO_FORMATS | VIDEO_FORMATS)[self.format_var.get()]
        job = Downloader(
            url,
            folder,
            fmt,
            QUALITIES[self.quality_var.get()],
            unique_stem(folder, name) if name else "",
            self.trim,
        )

        self._lock()
        self.progress["value"] = 0
        self.status_var.set("Preparando...")
        self.job = job
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

        if job.section:
            start, end = job.section
            opts.update(job.section_options())
            self.events.put(
                (App.MSG_STATUS, f"Recortando {format_time(start)} a {format_time(end)}...")
            )

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
        except Exception as exc:
            if not (job.section and self._is_partial_error(exc)):
                self.events.put((App.MSG_ERROR, exc))
                return
            self.events.put((App.MSG_STATUS, "Recorte no disponible, descargando completo..."))
            try:
                info = self._download_and_trim(job)
            except Exception as fallback:
                self.events.put((App.MSG_ERROR, fallback))
                return

        self.events.put((App.MSG_DONE, info))

    @staticmethod
    def _is_partial_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "partially" in text or "parcialmente" in text

    def _download_and_trim(self, job: Downloader) -> dict:
        yt_dlp = load_ytdlp()
        before = {entry.name for entry in os.scandir(job.folder)}
        opts = job.options()
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job.url, download=True)
        source = self._locate(job, info, before)
        staged = source.with_name(f"{source.stem}.recorte{source.suffix}")
        start, end = job.section
        trim_file(source, staged, start, end, job.fmt)
        staged.replace(source)
        info = dict(info)
        info["_filename"] = str(source)
        return info

    @staticmethod
    def _locate(job: Downloader, info: dict, before: set) -> Path:
        name = info.get("_filename") or info.get("filepath")
        if name and Path(str(name)).is_file():
            return Path(str(name))
        expected = job.folder / f"{job.stem}.{job.fmt}" if job.stem else None
        if expected and expected.is_file():
            return expected
        created = [p for p in job.folder.iterdir() if p.name not in before and p.is_file()]
        if len(created) == 1:
            return created[0]
        raise RuntimeError("No se encontro el archivo descargado para recortar.")

    def _poll(self) -> None:
        for kind, payload in self._drain(self.events):
            if kind == App.MSG_DOWNLOADING:
                self._on_progress(payload)
            elif kind == App.MSG_STATUS:
                self.status_var.set(payload)
            elif kind == App.MSG_DONE:
                self._on_done(payload)
            else:
                self._on_error(payload)

        for kind, payload in self._drain(self.meta):
            if kind == App.MSG_META:
                self._on_meta(payload)
            else:
                self._on_meta_error(payload)

        self.root.after(120, self._poll)

    @staticmethod
    def _drain(source: queue.Queue) -> list:
        items = []
        while True:
            try:
                items.append(source.get_nowait())
            except queue.Empty:
                return items

    def _on_progress(self, data: dict) -> None:
        status = data.get("status")

        if status == "processing":
            step = str(data.get("postprocessor") or "").lower()
            if "extractaudio" in step:
                self.status_var.set("Convirtiendo a audio...")
            elif "merger" in step:
                self.status_var.set("Uniendo video y audio...")
            else:
                self.status_var.set("Procesando archivo...")
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
        name = self._display_name(info)
        self.status_var.set(f"Listo: {name}")
        messagebox.showinfo(APP_NAME, f"Descarga completada:\n\n{name}")

    def _display_name(self, info: dict) -> str:
        path = info.get("_filename") or info.get("filepath")
        if path:
            return Path(str(path)).name
        job = self.job
        if job and job.stem:
            return f"{job.stem}.{job.fmt}"
        return str(info.get("title") or "archivo")

    def _on_error(self, exc: Exception) -> None:
        self._reset()
        self.status_var.set("Error en la descarga")
        messagebox.showerror(APP_NAME, f"No se pudo descargar:\n\n{exc}")

    def run(self) -> None:
        self.root.after(120, self._poll)
        self.root.mainloop()


def main() -> None:
    expose_ffmpeg()
    App(tk.Tk()).run()


if __name__ == "__main__":
    main()