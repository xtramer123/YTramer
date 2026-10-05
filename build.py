from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "programa"
BUILD_DIR = ROOT / ".build"
BIN_DIR = ROOT / "bin"

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"


def run(*args: str) -> None:
    print(f"\n> {' '.join(args)}")
    subprocess.run(args, check=True, cwd=ROOT)


def install_deps() -> None:
    run(sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp", "pyinstaller")


def fetch_from_zip(url: str, target: Path, label: str) -> Path:
    if target.is_file():
        print(f"\n{label} ya descargado.")
        return target

    BIN_DIR.mkdir(exist_ok=True)
    BUILD_DIR.mkdir(exist_ok=True)
    archive = BUILD_DIR / f"{target.stem}.zip"

    print(f"\nDescargando {label}...")
    urlretrieve(url, archive)

    with zipfile.ZipFile(archive) as zf:
        member = next(
            n for n in zf.namelist() if Path(n).name.lower() == target.name.lower()
        )
        with zf.open(member) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    archive.unlink()
    print(f"{label} listo: {target}")
    return target


def ensure_ffmpeg() -> Path:
    target = BIN_DIR / "ffmpeg.exe"
    if shutil.which("ffmpeg") and not target.is_file():
        print("\nffmpeg encontrado en el PATH, se usara ese.")
        return target
    return fetch_from_zip(FFMPEG_URL, target, "ffmpeg")


def ensure_deno() -> Path:
    target = BIN_DIR / "deno.exe"
    if shutil.which("deno") and not target.is_file():
        print("\ndeno encontrado en el PATH, se usara ese.")
        return target
    return fetch_from_zip(DENO_URL, target, "deno")


def build() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    binaries = [ensure_ffmpeg(), ensure_deno()]

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--clean",
        "--name",
        "YTramer",
        "--distpath",
        str(OUT_DIR),
        "--workpath",
        str(BUILD_DIR / "work"),
        "--specpath",
        str(BUILD_DIR),
        "--collect-all",
        "yt_dlp",
    ]

    for binary in binaries:
        args += ["--add-binary", f"{binary}{';'}."]

    args.append(str(ROOT / "main.py"))

    run(*args)

    exe = OUT_DIR / "YTramer.exe"
    size_mb = exe.stat().st_size / 1_048_576
    print("\n" + "=" * 46)
    print(f"Compilado con exito:  {exe}  ({size_mb:.0f} MB)")
    print("=" * 46)


if __name__ == "__main__":
    install_deps()
    build()