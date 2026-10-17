#!/usr/bin/env python3
"""Normalize product-video materials for faster editing.

Creates derived MP4 files in an output folder. Never edits source files.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    script_path = Path(__file__).resolve()
    for parent in [Path.cwd(), *script_path.parents]:
        bundled = parent / ".tools" / "bin" / f"{name}.exe"
        if bundled.exists():
            return str(bundled)
    roots = [
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
        Path("C:/Program Files (x86)/ffmpeg/bin"),
        Path.home() / "scoop/apps/ffmpeg/current/bin",
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
    ]
    exe = f"{name}.exe"
    for root in roots:
        if not root.exists():
            continue
        direct = root / exe
        if direct.exists():
            return str(direct)
        try:
            for candidate in root.rglob(exe):
                return str(candidate)
        except OSError:
            continue
    return None


def list_media(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS
            )
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            files.append(path)
    return sorted(set(files), key=lambda p: str(p).lower())


def safe_stem(path: Path, idx: int) -> str:
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", path.stem).strip("._-")
    if not stem:
        stem = "clip"
    return f"{idx:03d}_{stem}"


def video_filter(mode: str, size: str) -> str | None:
    if mode == "keep":
        return None
    width, height = size.split("x", 1)
    if mode == "pad":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def build_cmd(ffmpeg: str, src: Path, dst: Path, mode: str, size: str, crf: int, preset: str) -> list[str]:
    cmd = [ffmpeg, "-hide_banner", "-y", "-i", str(src)]
    vf = video_filter(mode, size)
    if vf:
        cmd.extend(["-vf", vf])
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    )
    return cmd


def run_one(args: tuple[str, int, Path, Path, str, str, int, str, bool]) -> tuple[Path, int, str]:
    ffmpeg, idx, src, out_dir, mode, size, crf, preset, dry_run = args
    dst = out_dir / f"{safe_stem(src, idx)}_h264_{size}.mp4"
    cmd = build_cmd(ffmpeg, src, dst, mode, size, crf, preset)
    if dry_run:
        return dst, 0, "DRY_RUN " + " ".join(cmd)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-8:]
        return dst, proc.returncode, "\n".join(tail)
    return dst, 0, "OK"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare playable H.264 MP4 assets for fast editing.")
    parser.add_argument("paths", nargs="+", type=Path, help="Video files or folders")
    parser.add_argument("--output", required=True, type=Path, help="Output folder for derived MP4 files")
    parser.add_argument("--fit", choices=["crop", "pad", "keep"], default="crop")
    parser.add_argument("--size", default="1080x1920", help="Output size, default 1080x1920")
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--preset", default="veryfast")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        print("ERROR: ffmpeg not found. Run employee environment setup or install FFmpeg.", file=sys.stderr)
        return 2

    files = list_media(args.paths)
    args.output.mkdir(parents=True, exist_ok=True)
    if not files:
        print("No video files found.")
        return 0

    jobs = max(1, min(args.jobs, len(files)))
    work = [
        (ffmpeg, idx, src, args.output, args.fit, args.size, args.crf, args.preset, args.dry_run)
        for idx, src in enumerate(files, 1)
    ]
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        for dst, code, msg in executor.map(run_one, work):
            if code == 0:
                print(f"OK {dst}")
            else:
                failures += 1
                print(f"FAIL {dst}\n{msg}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
