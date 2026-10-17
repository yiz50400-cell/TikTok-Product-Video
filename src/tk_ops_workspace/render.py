"""Showcase render core: plan/layout parsing, validation and FFmpeg filter-graph generation.

``scripts/render-video-showcase.ps1`` is a thin Windows wrapper around ``render showcase``.
Everything that decides *what* FFmpeg does lives here as pure, unit-tested functions.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .media import MediaToolError, find_tool, probe, probe_duration, run_tool, workspace_root
from .qa import QaSettings, run_qa

DEFAULT_TITLE = "Producto destacado"
DEFAULT_CTA = "Pídelo en el carrito"
SOURCE_END_TOLERANCE = 0.05

# Defaults reproduce the v0.2.0 hard-coded layout exactly.
DEFAULT_LAYOUT: dict[str, Any] = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf": 21,
    "fontfile": "",
    "title": {"y": 245, "font_size": 52, "min_font_size": 34, "max_lines": 2, "margin_x": 70,
              "duration": 3.0},
    "cta": {"y": 245, "font_size": 50, "min_font_size": 34, "max_lines": 2, "margin_x": 70,
            "duration": 3.0},
    "arrow": {"x": 165, "y": 1245, "width": 180, "bounce": 42, "period": 0.72},
    "cart": {"x": 365, "y": 1320, "width": 175},
    "text_style": {"fontcolor": "white", "borderw": 4, "bordercolor": "black@0.6", "box": True,
                   "boxcolor": "black@0.35", "boxborderw": 18},
}

FONT_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


class RenderError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    speed: float

    @property
    def output_duration(self) -> float:
        return (self.end - self.start) / self.speed


@dataclass(slots=True)
class Plan:
    segments: list[Segment]
    title: str = ""
    cta: str = ""
    layout: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_LAYOUT))

    @property
    def total_duration(self) -> float:
        return round(sum(s.output_duration for s in self.segments), 3)


@dataclass(frozen=True, slots=True)
class FittedText:
    lines: tuple[str, ...]
    font_size: int
    line_step: int
    overflow: bool = False


# ---------------------------------------------------------------- plan / layout

def merge_layout(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    layout = copy.deepcopy(DEFAULT_LAYOUT)
    for key, value in (overrides or {}).items():
        if key not in layout:
            raise RenderError(f"unknown layout key: {key!r}")
        if isinstance(layout[key], dict):
            if not isinstance(value, Mapping):
                raise RenderError(f"layout.{key} must be an object")
            for sub, sub_value in value.items():
                if sub not in layout[key]:
                    raise RenderError(f"unknown layout key: {key}.{sub}")
                layout[key][sub] = sub_value
        else:
            layout[key] = value
    for key in ("width", "height", "fps"):
        if not isinstance(layout[key], (int, float)) or layout[key] <= 0:
            raise RenderError(f"layout.{key} must be positive")
    for block in ("title", "cta"):
        b = layout[block]
        if not 8 <= b["min_font_size"] <= b["font_size"]:
            raise RenderError(f"layout.{block}: require 8 <= min_font_size <= font_size")
        if b["max_lines"] < 1 or b["duration"] <= 0:
            raise RenderError(f"layout.{block}: max_lines >= 1 and duration > 0")
    return layout


def parse_plan(payload: Mapping[str, Any]) -> Plan:
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise RenderError("segments JSON must contain at least one segment")
    segments = []
    for i, item in enumerate(raw_segments):
        try:
            seg = Segment(float(item["start"]), float(item["end"]), float(item.get("speed", 1.0)))
        except (KeyError, TypeError, ValueError) as error:
            raise RenderError(f"invalid segment at index {i}: {error}") from error
        if seg.start < 0 or seg.end <= seg.start or seg.speed <= 0:
            raise RenderError(
                f"invalid segment at index {i}: require start >= 0, end > start and speed > 0"
            )
        segments.append(seg)
    return Plan(
        segments=segments,
        title=str(payload.get("title") or ""),
        cta=str(payload.get("cta") or ""),
        layout=merge_layout(payload.get("layout")),
    )


def load_plan(path: Path) -> Plan:
    if not path.is_file():
        raise RenderError(f"segments JSON does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise RenderError(f"invalid segments JSON: {error}") from error
    if not isinstance(payload, dict):
        raise RenderError("segments JSON must be an object")
    return parse_plan(payload)


def validate_against_source(plan: Plan, source_duration: float) -> list[str]:
    """Fail before rendering when a segment reaches past the source (would freeze)."""
    errors = []
    for i, seg in enumerate(plan.segments):
        if seg.end > source_duration + SOURCE_END_TOLERANCE:
            errors.append(
                f"segment {i} ends at {seg.end:.3f}s but the source is only {source_duration:.3f}s"
            )
    if errors:
        raise RenderError(
            "segments exceed the source video (this would render frozen frames): "
            + "; ".join(errors)
        )
    warnings = []
    for i, seg in enumerate(plan.segments):
        if seg.output_duration < 0.3:
            warnings.append(f"segment_{i}_shorter_than_0.3s_after_speed")
    for i, (a, b) in enumerate(zip(plan.segments, plan.segments[1:], strict=False)):
        if b.start < a.end:
            warnings.append(f"segment_{i + 1}_overlaps_previous_segment")
    if plan.total_duration <= plan.layout["cta"]["duration"]:
        warnings.append("video_not_longer_than_cta_duration")
    return warnings


def layout_warnings(layout: Mapping[str, Any]) -> list[str]:
    w, h = layout["width"], layout["height"]
    warnings = []
    for name in ("arrow", "cart"):
        item = layout[name]
        if item["x"] < 0 or item["y"] < 0 or item["x"] + item["width"] > w or item["y"] >= h:
            warnings.append(f"{name}_outside_frame")
    if layout["arrow"]["y"] + layout["arrow"]["bounce"] > h * 0.85:
        warnings.append("arrow_in_lower_ui_safe_area")
    return warnings


# ---------------------------------------------------------------- text fitting

def _char_width(ch: str) -> float:
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if ch.isspace():
        return 0.3
    return 0.6


def text_width(text: str, font_size: float) -> float:
    """Conservative width estimate for a bold sans font (no font metrics needed)."""
    return sum(_char_width(ch) for ch in text) * font_size


def _wrap(text: str, font_size: int, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        tokens = paragraph.split(" ") if " " in paragraph else list(paragraph)
        joiner = " " if " " in paragraph else ""
        current = ""
        for token in tokens:
            candidate = f"{current}{joiner}{token}" if current else token
            if text_width(candidate, font_size) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = token
        lines.append(current)
    return [line.strip() for line in lines if line.strip()] or [""]


def fit_text(text: str, block: Mapping[str, Any], frame_width: int, boxborderw: int) -> FittedText:
    """Wrap and, if needed, shrink text so it fits ``max_lines`` inside the frame."""
    max_width = frame_width - 2 * block["margin_x"] - 2 * boxborderw
    size = int(block["font_size"])
    while True:
        lines = _wrap(text, size, max_width)
        fits = len(lines) <= block["max_lines"] and all(
            text_width(line, size) <= max_width for line in lines
        )
        if fits or size <= block["min_font_size"]:
            break
        size -= 2
    size = max(size, int(block["min_font_size"]))
    lines = _wrap(text, size, max_width)
    overflow = len(lines) > block["max_lines"] or any(
        text_width(line, size) > max_width for line in lines
    )
    step = round(size * 1.2 + boxborderw)
    return FittedText(tuple(lines), size, step, overflow)


# ---------------------------------------------------------------- filter graph

def _num(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _drawtext(
    textfile: str, fontfile: str | None, size: int, y: int, enable: str, style: Mapping[str, Any]
) -> str:
    parts = [f"textfile='{textfile}'"]
    if fontfile:
        parts.append(f"fontfile='{fontfile}'")
    parts += [
        f"enable='{enable}'",
        "x=(w-text_w)/2",
        f"y={y}",
        f"fontsize={size}",
        f"fontcolor={style['fontcolor']}",
        f"borderw={style['borderw']}",
        f"bordercolor={style['bordercolor']}",
    ]
    if style["box"]:
        parts += ["box=1", f"boxcolor={style['boxcolor']}", f"boxborderw={style['boxborderw']}"]
    return "drawtext=" + ":".join(parts)


def build_filter_graph(
    plan: Plan,
    *,
    title: FittedText,
    cta: FittedText,
    title_files: Sequence[str],
    cta_files: Sequence[str],
    fontfile: str | None,
) -> str:
    """Build the filter_complex graph. File references are relative to the FFmpeg cwd."""
    lay = plan.layout
    w, h = int(lay["width"]), int(lay["height"])
    total = plan.total_duration
    cta_start = round(max(0.0, total - float(lay["cta"]["duration"])), 3)
    style = lay["text_style"]
    graph: list[str] = []
    labels = []
    for i, seg in enumerate(plan.segments):
        graph.append(
            f"[0:v]trim=start={_num(seg.start)}:end={_num(seg.end)},"
            f"setpts=(PTS-STARTPTS)/{_num(seg.speed)},"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}[v{i}];"
        )
        labels.append(f"[v{i}]")
    graph.append("".join(labels) + f"concat=n={len(plan.segments)}:v=1:a=0[base];")
    current = "base"
    n = 0
    title_enable = f"between(t,0,{_num(float(lay['title']['duration']))})"
    for idx, path in enumerate(title_files):
        y = int(lay["title"]["y"]) + idx * title.line_step
        graph.append(f"[{current}]{_drawtext(path, fontfile, title.font_size, y, title_enable, style)}[t{n}];")
        current = f"t{n}"
        n += 1
    cta_enable = f"gte(t,{_num(cta_start)})"
    for idx, path in enumerate(cta_files):
        y = int(lay["cta"]["y"]) + idx * cta.line_step
        graph.append(f"[{current}]{_drawtext(path, fontfile, cta.font_size, y, cta_enable, style)}[t{n}];")
        current = f"t{n}"
        n += 1
    arrow, cart = lay["arrow"], lay["cart"]
    graph.append(
        f"[1:v]format=rgba,scale={int(arrow['width'])}:-1,trim=duration={_num(total)},"
        "setpts=PTS-STARTPTS[ar];"
    )
    graph.append(
        f"[2:v]format=rgba,scale={int(cart['width'])}:-1,trim=duration={_num(total)},"
        "setpts=PTS-STARTPTS[ca];"
    )
    graph.append(
        f"[{current}][ar]overlay=x={int(arrow['x'])}:"
        f"y='{int(arrow['y'])}+{_num(float(arrow['bounce']))}*sin(2*PI*t/{_num(float(arrow['period']))})':"
        f"enable='{cta_enable}'[u];"
    )
    graph.append(
        f"[u][ca]overlay=x={int(cart['x'])}:y={int(cart['y'])}:enable='{cta_enable}'[v]"
    )
    return "\n".join(graph)


def build_ffmpeg_args(
    ffmpeg: str, plan: Plan, graph: str, source: Path, arrow: Path, cart: Path, output: Path
) -> list[str]:
    lay = plan.layout
    return [
        ffmpeg, "-n", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-loop", "1", "-i", str(arrow),
        "-loop", "1", "-i", str(cart),
        "-filter_complex", graph,
        "-map", "[v]", "-an", "-t", _num(plan.total_duration),
        "-r", _num(float(lay["fps"])), "-c:v", "libx264", "-crf", str(lay["crf"]),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]


# ---------------------------------------------------------------- fonts

def resolve_fontfile(
    explicit: str | None, layout_value: str, plan_dir: Path | None
) -> tuple[Path | None, list[str]]:
    """explicit > layout.fontfile > $TK_VIDEO_FONTFILE > known system fonts."""
    for label, value in (("--fontfile", explicit), ("layout.fontfile", layout_value),
                         ("TK_VIDEO_FONTFILE", os.environ.get("TK_VIDEO_FONTFILE", ""))):
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            bases = [b for b in (plan_dir, workspace_root(), Path.cwd()) if b is not None]
            path = next((b / path for b in bases if (b / path).is_file()), bases[0] / path)
        if not path.is_file():
            raise RenderError(f"{label} does not exist: {path}")
        return path, []
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate), []
    return None, ["fontfile_not_found_using_ffmpeg_fontconfig_default"]


# ---------------------------------------------------------------- run

def _write_lines(work: Path, prefix: str, lines: Sequence[str]) -> list[str]:
    names = []
    for i, line in enumerate(lines):
        name = f"{prefix}_{i}.txt"
        (work / name).write_text(line, encoding="utf-8")
        names.append(name)
    return names


def render_showcase(
    *,
    source: Path,
    run_dir: Path,
    segments_json: Path | None = None,
    title: str = "",
    cta: str = "",
    output_name: str = "showcase.mp4",
    arrow_path: Path | None = None,
    cart_path: Path | None = None,
    fontfile: str | None = None,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    run_qa_check: bool = True,
) -> dict[str, Any]:
    root = workspace_root()
    source = source.resolve()
    run_dir = run_dir.resolve()
    if not source.is_file():
        raise RenderError(f"source video does not exist: {source}")
    segments_json = (segments_json or root / "config" / "video-showcase.example.json").resolve()
    plan = load_plan(segments_json)
    plan.title = title or plan.title or DEFAULT_TITLE
    plan.cta = cta or plan.cta or DEFAULT_CTA
    arrow = (arrow_path or root / "assets" / "video" / "overlays" / "preferred_down_arrow.png").resolve()
    cart = (cart_path or root / "assets" / "video" / "overlays" / "preferred_cart.png").resolve()
    for asset in (arrow, cart):
        if not asset.is_file():
            raise RenderError(f"overlay asset does not exist: {asset}")
    output = run_dir / output_name
    if output.exists():
        raise RenderError(f"output already exists: {output}. Use a new run dir; runs are never overwritten.")
    if output == source:
        raise RenderError("output would overwrite the source video")

    ffmpeg_path = find_tool("ffmpeg", ffmpeg)
    ffprobe_path = find_tool("ffprobe", ffprobe)
    source_duration = probe_duration(ffprobe_path, source)
    warnings = validate_against_source(plan, source_duration)  # raises before any write
    warnings += layout_warnings(plan.layout)
    font, font_warnings = resolve_fontfile(fontfile, plan.layout["fontfile"], segments_json.parent)
    warnings += font_warnings

    style = plan.layout["text_style"]
    fitted_title = fit_text(plan.title, plan.layout["title"], plan.layout["width"], style["boxborderw"])
    fitted_cta = fit_text(plan.cta, plan.layout["cta"], plan.layout["width"], style["boxborderw"])
    for name, fitted in (("title", fitted_title), ("cta", fitted_cta)):
        if fitted.overflow:
            warnings.append(f"{name}_too_long_even_at_min_font_size")

    run_dir.mkdir(parents=True, exist_ok=True)
    work = run_dir / "work"
    work.mkdir(exist_ok=True)
    font_ref = None
    if font is not None:
        font_ref = f"font{font.suffix.lower() or '.ttf'}"
        shutil.copyfile(font, work / font_ref)
    title_files = _write_lines(work, "title", fitted_title.lines)
    cta_files = _write_lines(work, "cta", fitted_cta.lines)
    graph = build_filter_graph(
        plan, title=fitted_title, cta=fitted_cta, title_files=title_files, cta_files=cta_files,
        fontfile=font_ref,
    )
    (work / "filter_graph.txt").write_text(graph, encoding="utf-8")
    # cwd=work keeps every filter path short and ASCII, so spaces/Chinese/quotes in user
    # paths never need filter escaping (inputs/outputs are plain argv entries).
    run_tool(build_ffmpeg_args(ffmpeg_path, plan, graph, source, arrow, cart, output), cwd=work)
    if not output.is_file():
        raise RenderError("render produced no output")
    probe_path = run_dir / "ffprobe.json"
    probe_path.write_text(json.dumps(probe(ffprobe_path, output), indent=2), encoding="utf-8")

    result: dict[str, Any] = {
        "output": str(output),
        "ffprobe": str(probe_path),
        "duration_seconds": plan.total_duration,
        "segment_count": len(plan.segments),
        "title": plan.title,
        "cta": plan.cta,
        "title_font_size": fitted_title.font_size,
        "title_lines": list(fitted_title.lines),
        "fontfile": str(font) if font else None,
        "source_duration_seconds": round(source_duration, 3),
        "warnings": warnings,
        "qa": None,
    }
    if run_qa_check:
        result["qa"] = run_qa(
            output,
            QaSettings(
                width=int(plan.layout["width"]),
                height=int(plan.layout["height"]),
                expected_duration=plan.total_duration,
                expected_fps=float(plan.layout["fps"]),
            ),
            ffmpeg=ffmpeg_path,
            ffprobe=ffprobe_path,
        )
    return result


def add_render_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("render", help="render product showcase videos")
    nested = parser.add_subparsers(dest="render_command", required=True)
    s = nested.add_parser("showcase")
    s.add_argument("--source", type=Path, required=True)
    s.add_argument("--run-dir", type=Path, required=True)
    s.add_argument("--segments-json", type=Path)
    s.add_argument("--title", default="")
    s.add_argument("--cta", default="")
    s.add_argument("--output-name", default="showcase.mp4")
    s.add_argument("--arrow-path", type=Path)
    s.add_argument("--cart-path", type=Path)
    s.add_argument("--fontfile", default="")
    s.add_argument("--ffmpeg", default="")
    s.add_argument("--ffprobe", default="")
    s.add_argument("--skip-qa", action="store_true")
    s.add_argument("--plan-only", action="store_true",
                   help="validate plan + print the filter graph without rendering")


def handle_render(ns: argparse.Namespace) -> int:
    if ns.render_command != "showcase":
        return 2
    try:
        if ns.plan_only:
            plan = load_plan(ns.segments_json or workspace_root() / "config" / "video-showcase.example.json")
            title = fit_text(ns.title or plan.title or DEFAULT_TITLE, plan.layout["title"],
                             plan.layout["width"], plan.layout["text_style"]["boxborderw"])
            cta = fit_text(ns.cta or plan.cta or DEFAULT_CTA, plan.layout["cta"],
                           plan.layout["width"], plan.layout["text_style"]["boxborderw"])
            graph = build_filter_graph(
                plan, title=title, cta=cta,
                title_files=[f"title_{i}.txt" for i in range(len(title.lines))],
                cta_files=[f"cta_{i}.txt" for i in range(len(cta.lines))], fontfile="font.ttf",
            )
            print(json.dumps({"duration_seconds": plan.total_duration, "graph": graph}, indent=2))
            return 0
        result = render_showcase(
            source=ns.source, run_dir=ns.run_dir, segments_json=ns.segments_json,
            title=ns.title, cta=ns.cta, output_name=ns.output_name, arrow_path=ns.arrow_path,
            cart_path=ns.cart_path, fontfile=ns.fontfile or None, ffmpeg=ns.ffmpeg or None,
            ffprobe=ns.ffprobe or None, run_qa_check=not ns.skip_qa,
        )
    except (RenderError, MediaToolError, OSError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=True, indent=2))
        return 2
    qa = result.get("qa")
    result["status"] = "ok" if qa is None or qa.get("passed") else "qa_failed"
    print(json.dumps(result, ensure_ascii=True, indent=2))
    sys.stdout.flush()
    return 0 if result["status"] == "ok" else 3


__all__ = [
    "DEFAULT_LAYOUT", "FittedText", "Plan", "RenderError", "Segment", "add_render_parser",
    "build_ffmpeg_args", "build_filter_graph", "fit_text", "handle_render", "load_plan",
    "merge_layout", "parse_plan", "render_showcase", "resolve_fontfile", "text_width",
    "validate_against_source",
]
