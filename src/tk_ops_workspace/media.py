"""Shared FFmpeg/FFprobe helpers (tool discovery, subprocess, probing)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


class MediaToolError(Exception):
    pass


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def find_tool(name: str, explicit: str | os.PathLike[str] | None = None) -> str:
    """Resolve ffmpeg/ffprobe: explicit path > ``.tools/bin`` > PATH."""
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise MediaToolError(f"tool does not exist: {path}")
        return str(path)
    bundled_dir = workspace_root() / ".tools" / "bin"
    for candidate in (bundled_dir / f"{name}.exe", bundled_dir / name):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise MediaToolError(f"missing {name}: install FFmpeg or pass its path")
    return found


def run_tool(
    cmd: Sequence[str], *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [str(part) for part in cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.strip()[-1200:]
        raise MediaToolError(f"{Path(cmd[0]).name} failed with exit code {proc.returncode}: {tail}")
    return proc


def probe(ffprobe: str, path: Path) -> dict[str, object]:
    out = run_tool(
        [
            ffprobe, "-v", "error",
            "-show_entries",
            (
                "format=duration:stream=index,codec_type,codec_name,width,height,pix_fmt,"
                "r_frame_rate,avg_frame_rate,channels,sample_rate"
            ),
            "-of", "json", str(path),
        ]
    )
    return json.loads(out.stdout)


def probe_duration(ffprobe: str, path: Path) -> float:
    data = probe(ffprobe, path)
    try:
        return float(data["format"]["duration"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError) as error:
        raise MediaToolError(f"cannot read duration of {path}") from error


def parse_rate(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    if "/" in value:
        num, _, den = value.partition("/")
        try:
            den_f = float(den)
            return float(num) / den_f if den_f else None
        except ValueError:
            return None
    try:
        return float(value)
    except ValueError:
        return None
