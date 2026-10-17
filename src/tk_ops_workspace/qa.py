"""Delivery QA: codec/size/pix_fmt, expected duration, fps, audio, freeze detection."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .media import MediaToolError, find_tool, parse_rate, probe, run_tool

FREEZE_RE = re.compile(r"lavfi\.freezedetect\.freeze_(start|duration|end):\s*([0-9.]+)")


@dataclass(frozen=True, slots=True)
class QaSettings:
    width: int = 1080
    height: int = 1920
    expected_duration: float | None = None
    duration_tolerance: float = 0.25
    expected_fps: float | None = 30.0
    fps_tolerance: float = 0.05
    require_audio: bool = False
    freeze_max_seconds: float = 0.8
    freeze_noise: float = 0.003
    check_freezes: bool = True


def parse_freezes(stderr: str, total_duration: float | None = None) -> list[dict[str, float]]:
    """Parse freezedetect log lines into ``[{start, end, duration}]``.

    A freeze still open at the end of the file is closed at ``total_duration``.
    """
    freezes: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    for kind, value in FREEZE_RE.findall(stderr):
        number = float(value)
        if kind == "start":
            current = {"start": number}
            freezes.append(current)
        elif current is not None and kind == "duration":
            current["duration"] = number
        elif current is not None and kind == "end":
            current["end"] = number
            current.setdefault("duration", round(number - current["start"], 3))
            current = None
    for item in freezes:
        if "end" not in item:
            end = total_duration if total_duration is not None else item["start"]
            item["end"] = round(end, 3)
            item["duration"] = round(end - item["start"], 3)
            item["open_at_end"] = 1.0
    return freezes


def detect_freezes(ffmpeg: str, path: Path, settings: QaSettings, total: float | None) -> list[dict[str, float]]:
    proc = run_tool(
        [
            ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
            "-vf", f"freezedetect=n={settings.freeze_noise}:d={settings.freeze_max_seconds}",
            "-map", "0:v:0", "-f", "null", "-",
        ]
    )
    return parse_freezes(proc.stderr, total)


def evaluate(
    probe_data: Mapping[str, object],
    settings: QaSettings,
    freezes: Sequence[Mapping[str, float]] | None = None,
) -> dict[str, object]:
    """Pure evaluation of probe data (+ optional freezes) against delivery settings."""
    streams = list(probe_data.get("streams") or [])  # type: ignore[arg-type]
    fmt = probe_data.get("format") or {}
    video = next(
        (s for s in streams if s.get("codec_type") == "video" or (
            "codec_type" not in s and s.get("codec_name") == "h264")),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    try:
        duration = float(fmt.get("duration"))  # type: ignore[union-attr,arg-type]
    except (TypeError, ValueError):
        duration = 0.0
    errors: list[str] = []
    warnings: list[str] = []
    fps = None
    if video is None or video.get("codec_name") != "h264":
        errors.append("missing_h264_video_stream")
    if video is not None:
        if video.get("width") != settings.width or video.get("height") != settings.height:
            errors.append(f"expected_{settings.width}x{settings.height}")
        if video.get("pix_fmt") != "yuv420p":
            errors.append("expected_yuv420p")
        fps = parse_rate(video.get("avg_frame_rate")) or parse_rate(video.get("r_frame_rate"))
        if settings.expected_fps is not None and (
            fps is None or abs(fps - settings.expected_fps) > settings.fps_tolerance
        ):
            errors.append(f"expected_fps_{settings.expected_fps:g}")
    if duration <= 0:
        errors.append("invalid_duration")
    duration_delta = None
    if settings.expected_duration is not None and duration > 0:
        duration_delta = round(duration - settings.expected_duration, 3)
        if abs(duration_delta) > settings.duration_tolerance:
            errors.append("duration_mismatch")
    if settings.require_audio:
        if audio is None:
            errors.append("missing_audio_stream")
        elif audio.get("codec_name") != "aac":
            errors.append("expected_aac_audio")
    long_freezes: list[Mapping[str, float]] = []
    if freezes is not None:
        long_freezes = [f for f in freezes if f.get("duration", 0) >= settings.freeze_max_seconds]
        if long_freezes:
            errors.append("freeze_detected")
    elif settings.check_freezes:
        warnings.append("freeze_check_not_run")
    return {
        "duration_seconds": round(duration, 3),
        "expected_duration_seconds": settings.expected_duration,
        "duration_delta_seconds": duration_delta,
        "h264": video is not None and video.get("codec_name") == "h264",
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
        "pix_fmt": video.get("pix_fmt") if video else None,
        "fps": round(fps, 3) if fps else None,
        "audio": audio is not None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "freezes": [dict(f) for f in (freezes or [])],
        "freeze_max_seconds": settings.freeze_max_seconds,
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
    }


def unique_report_path(video: Path, explicit: Path | None = None) -> Path:
    if explicit is not None:
        if explicit.exists():
            raise MediaToolError(f"refusing to overwrite existing QA report: {explicit}")
        return explicit
    base = video.with_name(f"{video.stem}.qa.json")
    if not base.exists():
        return base
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return video.with_name(f"{video.stem}.qa.{stamp}.json")


def run_qa(
    video: Path,
    settings: QaSettings,
    *,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    report_path: Path | None = None,
    write_report: bool = True,
) -> dict[str, object]:
    if not video.is_file():
        raise MediaToolError(f"video does not exist: {video}")
    ffprobe_path = find_tool("ffprobe", ffprobe)
    data = probe(ffprobe_path, video)
    freezes = None
    if settings.check_freezes:
        try:
            total = float(data["format"]["duration"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            total = None
        freezes = detect_freezes(find_tool("ffmpeg", ffmpeg), video, settings, total)
    result = {"video": str(video), **evaluate(data, settings, freezes)}
    result["checked_at"] = datetime.now(UTC).isoformat()
    if write_report:
        path = unique_report_path(video, report_path)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["qa_json"] = str(path)
    return result


def add_verify_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser("verify", help="delivery QA for a rendered MP4")
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--expected-duration", type=float)
    p.add_argument("--duration-tolerance", type=float, default=0.25)
    p.add_argument("--expected-fps", type=float, default=30.0, help="0 disables the fps check")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--require-audio", action="store_true")
    p.add_argument("--freeze-max-seconds", type=float, default=0.8)
    p.add_argument("--skip-freeze-check", action="store_true")
    p.add_argument("--qa-json", type=Path, help="report path (default: <video>.qa.json, never overwritten)")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--ffmpeg", default="")
    p.add_argument("--ffprobe", default="")


def handle_verify(ns: argparse.Namespace) -> int:
    settings = QaSettings(
        width=ns.width,
        height=ns.height,
        expected_duration=ns.expected_duration,
        duration_tolerance=ns.duration_tolerance,
        expected_fps=ns.expected_fps or None,
        require_audio=ns.require_audio,
        freeze_max_seconds=ns.freeze_max_seconds,
        check_freezes=not ns.skip_freeze_check,
    )
    try:
        result = run_qa(
            ns.video.resolve(),
            settings,
            ffmpeg=ns.ffmpeg or None,
            ffprobe=ns.ffprobe or None,
            report_path=ns.qa_json.resolve() if ns.qa_json else None,
            write_report=not ns.no_report,
        )
    except MediaToolError as error:
        print(json.dumps({"passed": False, "errors": ["qa_failed"], "message": str(error)}))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1
