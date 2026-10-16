#!/usr/bin/env python3
"""Fast preflight for product-video source materials.

Reads media metadata with ffprobe and optionally runs ffmpeg freezedetect.
It never edits source files.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
SAFE_VIDEO_CODECS = {"h264"}
SAFE_AUDIO_CODECS = {"aac", ""}


@dataclass
class Tooling:
    ffprobe: str | None
    ffmpeg: str | None


def find_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    script_path = Path(__file__).resolve()
    for parent in [Path.cwd(), *script_path.parents]:
        bundled = parent / ".tools" / "bin" / f"{name}.exe"
        if bundled.exists():
            return str(bundled)
    common_roots = [
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
        Path("C:/Program Files (x86)/ffmpeg/bin"),
        Path.home() / "scoop/apps/ffmpeg/current/bin",
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
    ]
    exe = f"{name}.exe"
    for root in common_roots:
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
    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            out.extend(
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS
            )
        elif path.is_file() and path.suffix.lower() in VIDEO_EXTS:
            out.append(path)
    return sorted(set(out), key=lambda p: str(p).lower())


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "command failed")
    return json.loads(proc.stdout)


def probe(path: Path, ffprobe: str | None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "file": str(path),
        "exists": path.exists(),
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2) if path.exists() else None,
    }
    if not ffprobe:
        item["error"] = "ffprobe not found"
        return item
    try:
        data = run_json(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        item["error"] = str(exc)
        return item

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    vcodec = str(video.get("codec_name") or "")
    acodec = str(audio.get("codec_name") or "")
    pix_fmt = str(video.get("pix_fmt") or "")
    duration = float(fmt.get("duration") or video.get("duration") or 0)
    item.update(
        {
            "duration_s": round(duration, 2),
            "width": width,
            "height": height,
            "aspect": f"{width}:{height}" if width and height else "",
            "vertical": bool(height > width and width > 0),
            "codec_video": vcodec,
            "codec_audio": acodec,
            "pix_fmt": pix_fmt,
            "playable_primary": (
                vcodec in SAFE_VIDEO_CODECS
                and acodec in SAFE_AUDIO_CODECS
                and (pix_fmt == "yuv420p" or not pix_fmt)
                and path.suffix.lower() == ".mp4"
            ),
        }
    )
    return item


def detect_freezes(path: Path, ffmpeg: str | None, threshold: float) -> dict[str, Any]:
    if not ffmpeg:
        return {"freeze_check": "skipped: ffmpeg not found"}
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-vf",
        f"freezedetect=n=-60dB:d={threshold}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    text = proc.stderr + "\n" + proc.stdout
    starts = [line.strip() for line in text.splitlines() if "freeze_start:" in line]
    durations = [line.strip() for line in text.splitlines() if "freeze_duration:" in line]
    return {
        "freeze_check": "ok" if proc.returncode == 0 else "ffmpeg returned non-zero",
        "freeze_start_count": len(starts),
        "freeze_duration_count": len(durations),
        "freeze_lines": (starts + durations)[:20],
    }


def print_text(results: list[dict[str, Any]], tooling: Tooling) -> None:
    print(f"ffprobe: {tooling.ffprobe or 'NOT_FOUND'}")
    print(f"ffmpeg:  {tooling.ffmpeg or 'NOT_FOUND'}")
    print(f"files:   {len(results)}")
    print()
    for idx, item in enumerate(results, 1):
        name = Path(item["file"]).name
        if item.get("error"):
            print(f"{idx}. {name} | ERROR: {item['error']}")
            continue
        flags = []
        flags.append("VERTICAL" if item.get("vertical") else "NOT_VERTICAL")
        flags.append("PLAYABLE" if item.get("playable_primary") else "NEEDS_TRANSCODE")
        if item.get("freeze_start_count"):
            flags.append(f"FREEZE_RISK={item.get('freeze_start_count')}")
        print(
            f"{idx}. {name} | {item.get('duration_s')}s | "
            f"{item.get('width')}x{item.get('height')} | "
            f"v={item.get('codec_video')} a={item.get('codec_audio')} "
            f"pix={item.get('pix_fmt')} | {', '.join(flags)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe product-video source materials quickly.")
    parser.add_argument("paths", nargs="+", type=Path, help="Files or folders to scan recursively")
    parser.add_argument("--freeze", action="store_true", help="Run ffmpeg freezedetect too")
    parser.add_argument("--freeze-threshold", type=float, default=0.8)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of compact text")
    args = parser.parse_args()

    tooling = Tooling(ffprobe=find_tool("ffprobe"), ffmpeg=find_tool("ffmpeg"))
    files = list_media(args.paths)
    results = []
    for file in files:
        item = probe(file, tooling.ffprobe)
        if args.freeze and not item.get("error"):
            item.update(detect_freezes(file, tooling.ffmpeg, args.freeze_threshold))
        results.append(item)

    payload = {
        "tooling": {"ffprobe": tooling.ffprobe, "ffmpeg": tooling.ffmpeg},
        "count": len(results),
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(results, tooling)
    return 0


if __name__ == "__main__":
    sys.exit(main())
