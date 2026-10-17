"""Scripted voiceover (TTS) + phrase-synced SRT + AAC mux for approved, localized scripts.

Gates that are never bypassed here:
- the localized script must carry an explicit approval (``approved_by``);
- the localized text must pass ``video-compliance`` (status ``passed``) before any TTS runs;
- source video and previous outputs are never overwritten (existing outputs abort the run).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import shutil
import subprocess
import sys
import wave
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .video_compliance import check_video_compliance

SAMPLE_RATE = 24000

# market/language -> defaults. Kokoro has no Indonesian voice; auto falls back to edge-tts.
LANGUAGES: dict[str, dict[str, str]] = {
    "es-MX": {"kokoro_lang": "e", "kokoro_voice": "ef_dora", "edge_voice": "es-MX-DaliaNeural"},
    "pt-BR": {"kokoro_lang": "p", "kokoro_voice": "pf_dora", "edge_voice": "pt-BR-FranciscaNeural"},
    "id-ID": {"kokoro_lang": "", "kokoro_voice": "", "edge_voice": "id-ID-GadisNeural"},
}
MARKET_LANGUAGE = {
    "mexico": "es-MX", "mx": "es-MX", "墨西哥": "es-MX",
    "brazil": "pt-BR", "brasil": "pt-BR", "br": "pt-BR", "巴西": "pt-BR",
    "indonesia": "id-ID", "id": "id-ID", "印尼": "id-ID", "印度尼西亚": "id-ID",
}
BACKENDS = ("auto", "kokoro", "edge-tts", "silent")


class VoiceoverError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Phrase:
    text: str
    start: float | None = None
    end: float | None = None


@dataclass(frozen=True, slots=True)
class VoiceScript:
    language: str
    phrases: tuple[Phrase, ...]
    approved_by: str = ""


@dataclass(frozen=True, slots=True)
class Cue:
    index: int
    start: float
    end: float
    text: str


@dataclass(slots=True)
class FitResult:
    tempo: float
    starts: list[float]
    durations: list[float]
    voice_end: float
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- parsing

def normalize_language(value: str) -> str:
    raw = value.strip()
    for code in LANGUAGES:
        if raw.lower().replace("_", "-") == code.lower():
            return code
    mapped = MARKET_LANGUAGE.get(raw.lower())
    if mapped:
        return mapped
    raise VoiceoverError(f"unsupported language/market: {value!r} (use es-MX, pt-BR, id-ID)")


def parse_script_text(text: str, *, suffix: str, language: str = "") -> VoiceScript:
    """Parse a localized script. ``.txt``: one phrase per line, ``#`` comments.

    ``.json``: ``{"language": "es-MX", "approved_by": "...", "phrases": ["..." | {"text", "start", "end"}]}``
    """
    if suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise VoiceoverError(f"invalid JSON script: {error}") from error
        if isinstance(payload, list):
            payload = {"phrases": payload}
        if not isinstance(payload, dict):
            raise VoiceoverError("JSON script must be an object or list")
        items = payload.get("phrases")
        if not isinstance(items, list):
            raise VoiceoverError("JSON script needs a 'phrases' list")
        phrases = []
        for i, item in enumerate(items):
            if isinstance(item, str):
                item = {"text": item}
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                raise VoiceoverError(f"phrase {i} has no text")
            start, end = item.get("start"), item.get("end")
            start = None if start is None else float(start)
            end = None if end is None else float(end)
            if start is not None and end is not None and end <= start:
                raise VoiceoverError(f"phrase {i}: end must be greater than start")
            phrases.append(Phrase(str(item["text"]).strip(), start, end))
        lang = language or str(payload.get("language", ""))
        approved_by = str(payload.get("approved_by", "")).strip()
    else:
        phrases = [
            Phrase(line.strip())
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        lang, approved_by = language, ""
    if not phrases:
        raise VoiceoverError("script has no phrases")
    if not lang:
        raise VoiceoverError("language is required (--language or JSON 'language')")
    timed = [p.start is not None for p in phrases]
    if any(timed) and not all(timed):
        raise VoiceoverError("either all phrases have 'start' or none do")
    if all(timed):
        starts = [p.start for p in phrases]
        if any(b < a for a, b in itertools.pairwise(starts)):
            raise VoiceoverError("phrase start times must be ascending")
    return VoiceScript(normalize_language(lang), tuple(phrases), approved_by)


def load_script(path: Path, language: str = "") -> VoiceScript:
    return parse_script_text(path.read_text(encoding="utf-8-sig"), suffix=path.suffix, language=language)


# ---------------------------------------------------------------- timing

def estimate_speech_seconds(text: str, chars_per_second: float = 14.0) -> float:
    """Rough duration used by the silent backend (and for planning)."""
    return round(max(0.6, len(text.strip()) / chars_per_second), 3)


def fit_timeline(
    durations: Sequence[float],
    video_duration: float,
    *,
    fixed_starts: Sequence[float] | None = None,
    lead_in: float = 0.3,
    gap: float = 0.15,
    tail: float = 0.3,
    max_tempo: float = 1.25,
    min_fill: float = 0.7,
    max_gap: float = 0.6,
) -> FitResult:
    """Place phrases on the video timeline.

    - Overrun: speed voice up (atempo) up to ``max_tempo``; beyond that it is an error.
    - Underfill (voice ends before ``min_fill`` of the video): widen gaps up to ``max_gap``
      and warn if it still ends early. Voice is never slowed down.
    """
    if video_duration <= 0:
        raise VoiceoverError("video duration must be positive")
    if not durations or any(d <= 0 for d in durations):
        raise VoiceoverError("phrase durations must be positive")
    warnings: list[str] = []
    available = video_duration - tail
    if fixed_starts is not None:
        if len(fixed_starts) != len(durations):
            raise VoiceoverError("fixed_starts length mismatch")
        tempo = 1.0
        for i, start in enumerate(fixed_starts):
            limit = fixed_starts[i + 1] - 0.05 if i + 1 < len(fixed_starts) else available
            room = limit - start
            if room <= 0:
                raise VoiceoverError(f"phrase {i + 1} starts after the usable video end")
            tempo = max(tempo, durations[i] / room)
        tempo = math.ceil(tempo * 1000) / 1000
        if tempo > max_tempo:
            raise VoiceoverError(
                f"voice needs tempo {tempo:.2f}x to fit the given timings (max {max_tempo}); "
                "shorten the script or loosen timings"
            )
        if tempo > 1.0:
            warnings.append(f"voice_sped_up_{tempo:.2f}x_to_fit_timings")
        scaled = [math.floor(d / tempo * 1000) / 1000 for d in durations]
        starts = [round(float(s), 3) for s in fixed_starts]
    else:
        n = len(durations)
        speech = sum(durations)
        needed = lead_in + speech + gap * (n - 1)
        tempo = 1.0
        if needed > available:
            room = available - lead_in - gap * (n - 1)
            tempo = math.ceil(speech / room * 1000) / 1000 if room > 0 else math.inf
            if tempo > max_tempo:
                raise VoiceoverError(
                    f"voice ({needed:.2f}s) overruns video ({video_duration:.2f}s); would need "
                    f"{tempo:.2f}x (max {max_tempo}). Shorten the approved script."
                )
            warnings.append(f"voice_sped_up_{tempo:.2f}x_to_fit_video")
        scaled = [math.floor(d / tempo * 1000) / 1000 for d in durations]
        speech = sum(scaled)
        used_gap = gap
        end = lead_in + speech + gap * (n - 1)
        if n > 1 and end < min_fill * video_duration:
            want = (min_fill * video_duration - lead_in - speech) / (n - 1)
            used_gap = min(max_gap, max(gap, want))
        starts, t = [], lead_in
        for d in scaled:
            starts.append(round(t, 3))
            t += d + used_gap
    voice_end = round(starts[-1] + scaled[-1], 3)
    if voice_end < min_fill * video_duration:
        warnings.append(
            f"voice_ends_early_{voice_end:.2f}s_of_{video_duration:.2f}s; consider a longer approved script"
        )
    if voice_end > video_duration:
        raise VoiceoverError("voice still overruns video after fitting")
    return FitResult(tempo, starts, scaled, voice_end, warnings)


def wrap_subtitle(text: str, max_chars: int = 32) -> str:
    words = text.split()
    if len(text) <= max_chars or len(words) < 2:
        return text
    best, best_score = text, math.inf
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        score = max(len(a), len(b))
        if score < best_score:
            best, best_score = f"{a}\n{b}", score
    return best


def build_cues(phrases: Sequence[Phrase], fit: FitResult, video_duration: float) -> list[Cue]:
    cues = []
    for i, phrase in enumerate(phrases):
        start = fit.starts[i]
        end = start + fit.durations[i]
        if phrase.end is not None:
            end = max(end, phrase.end)
        if i + 1 < len(phrases):
            end = min(end + 0.1, fit.starts[i + 1] - 0.02)
        end = min(end, video_duration)
        cues.append(Cue(i + 1, round(start, 3), round(max(end, start + 0.2), 3), wrap_subtitle(phrase.text)))
    return cues


def format_srt_time(seconds: float) -> str:
    ms = round(max(0.0, seconds) * 1000)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(cues: Sequence[Cue]) -> str:
    blocks = [
        f"{c.index}\n{format_srt_time(c.start)} --> {format_srt_time(c.end)}\n{c.text}\n"
        for c in cues
    ]
    return "\n".join(blocks)


# ---------------------------------------------------------------- tools / backends

def _tool(name: str, explicit: str = "") -> str:
    if explicit:
        return explicit
    found = shutil.which(name)
    if not found:
        raise VoiceoverError(f"{name} not found on PATH")
    return found


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(cmd), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if proc.returncode != 0:
        raise VoiceoverError(f"command failed ({proc.returncode}): {cmd[0]} ... {proc.stderr[-800:]}")
    return proc


def probe_duration(ffprobe: str, path: Path) -> float:
    out = _run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)])
    return float(json.loads(out.stdout)["format"]["duration"])


def kokoro_available() -> bool:
    return importlib.util.find_spec("kokoro") is not None and importlib.util.find_spec("soundfile") is not None


def edge_tts_available() -> bool:
    return importlib.util.find_spec("edge_tts") is not None or shutil.which("edge-tts") is not None


def resolve_backend(requested: str, language: str) -> str:
    if requested != "auto":
        if requested == "kokoro" and not LANGUAGES[language]["kokoro_lang"]:
            raise VoiceoverError(f"Kokoro has no voice for {language}; use --backend edge-tts")
        if requested == "kokoro" and not kokoro_available():
            raise VoiceoverError("kokoro not installed: uv sync --extra kokoro")
        if requested == "edge-tts" and not edge_tts_available():
            raise VoiceoverError("edge-tts not installed: uv sync --extra edge-tts")
        return requested
    if LANGUAGES[language]["kokoro_lang"] and kokoro_available():
        return "kokoro"
    if edge_tts_available():
        return "edge-tts"
    raise VoiceoverError(
        "no TTS backend available for auto: install `uv sync --extra kokoro` or "
        "`uv sync --extra edge-tts` (use --backend silent only for testing)"
    )


def default_voice(backend: str, language: str) -> str:
    if backend == "kokoro":
        return LANGUAGES[language]["kokoro_voice"]
    if backend == "edge-tts":
        return LANGUAGES[language]["edge_voice"]
    return "silent"


class _Synth:
    def __init__(self, backend: str, language: str, voice: str, speed: float, ffmpeg: str):
        self.backend, self.language, self.voice, self.speed, self.ffmpeg = backend, language, voice, speed, ffmpeg
        self._pipeline = None

    def raw(self, text: str, dest_stem: Path) -> Path:
        if self.backend == "silent":
            out = dest_stem.with_suffix(".wav")
            frames = int(estimate_speech_seconds(text) / self.speed * SAMPLE_RATE)
            _write_wav(out, b"\x00\x00" * frames)
            return out
        if self.backend == "edge-tts":
            out = dest_stem.with_suffix(".mp3")
            rate = f"{round((self.speed - 1) * 100):+d}%"
            cmd = [sys.executable, "-m", "edge_tts"] if importlib.util.find_spec("edge_tts") else ["edge-tts"]
            _run([*cmd, "--voice", self.voice, f"--rate={rate}", "--text", text, "--write-media", str(out)])
            return out
        if self.backend == "kokoro":
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline

            if self._pipeline is None:
                self._pipeline = KPipeline(lang_code=LANGUAGES[self.language]["kokoro_lang"])
            chunks = [audio for _, _, audio in self._pipeline(text, voice=self.voice, speed=self.speed)]
            if not chunks:
                raise VoiceoverError(f"kokoro produced no audio for: {text!r}")
            out = dest_stem.with_suffix(".wav")
            sf.write(str(out), np.concatenate([np.asarray(c) for c in chunks]), SAMPLE_RATE)
            return out
        raise VoiceoverError(f"unknown backend {self.backend}")


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def _normalize(ffmpeg: str, src: Path, dest: Path, tempo: float = 1.0) -> float:
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if abs(tempo - 1.0) > 1e-3:
        args += ["-filter:a", f"atempo={tempo:.3f}"]
    _run([*args, "-ac", "1", "-ar", str(SAMPLE_RATE), "-sample_fmt", "s16", str(dest)])
    with wave.open(str(dest), "rb") as w:
        return w.getnframes() / SAMPLE_RATE


def assemble_track(clips: Sequence[Path], starts: Sequence[float], total: float, dest: Path) -> None:
    total_frames = round(total * SAMPLE_RATE)
    buf = bytearray(b"\x00\x00" * total_frames)
    for clip, start in zip(clips, starts, strict=True):
        pcm = _read_pcm(clip)
        offset = round(start * SAMPLE_RATE) * 2
        pcm = pcm[: max(0, len(buf) - offset)]
        buf[offset : offset + len(pcm)] = pcm
    _write_wav(dest, bytes(buf))


def _filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- main flow

def build_voiceover(ns: argparse.Namespace) -> dict[str, object]:
    script_path: Path = ns.script.resolve()
    video: Path = ns.video.resolve()
    run_dir: Path = ns.run_dir.resolve()
    if not video.is_file():
        raise VoiceoverError(f"video not found: {video}")
    script = load_script(script_path, ns.language or "")

    approved_by = (ns.approved_by or script.approved_by).strip()
    if not approved_by:
        raise VoiceoverError(
            "approval gate: the localized script is not marked approved. Show the exact Chinese "
            "voiceover draft, get approval, then pass --approved-by NAME (or JSON 'approved_by')."
        )

    full_text = "\n".join(p.text for p in script.phrases)
    report = check_video_compliance(
        fields={"script": full_text, "subtitles": full_text},
        market=ns.market,
        category=ns.category,
        ai_generated=ns.ai_generated,
        ai_label_enabled=ns.ai_label_enabled,
    )
    if report.status != "passed":
        raise VoiceoverError(
            "compliance gate blocked: " + json.dumps(report.to_dict(), ensure_ascii=False)
        )

    stem = ns.output_stem or video.stem
    outputs = {
        "video": run_dir / f"{stem}.voiced.mp4",
        "srt": run_dir / f"{stem}.{script.language}.srt",
        "audio": run_dir / f"{stem}.voice.wav",
        "notes": run_dir / f"{stem}.voiceover-notes.json",
    }
    if ns.burn_subtitles:
        outputs["burned"] = run_dir / f"{stem}.voiced.subtitled.mp4"
    for path in outputs.values():
        if path.exists():
            raise VoiceoverError(f"refusing to overwrite existing output: {path} (use a new run dir)")
        if path == video or path == script_path:
            raise VoiceoverError("output would overwrite an input file")

    ffmpeg = _tool("ffmpeg", ns.ffmpeg or "")
    ffprobe = _tool("ffprobe", ns.ffprobe or "")
    video_duration = probe_duration(ffprobe, video)
    backend = resolve_backend(ns.backend, script.language)
    voice = ns.voice or default_voice(backend, script.language)

    run_dir.mkdir(parents=True, exist_ok=True)
    work = run_dir / f"{stem}.voiceover-work"
    if work.exists():
        raise VoiceoverError(f"refusing to reuse work dir: {work}")
    work.mkdir()

    synth = _Synth(backend, script.language, voice, ns.speed, ffmpeg)
    raw_durations = []
    for i, phrase in enumerate(script.phrases):
        raw = synth.raw(phrase.text, work / f"raw_{i:03d}")
        raw_durations.append(_normalize(ffmpeg, raw, work / f"norm_{i:03d}.wav"))

    fixed = [p.start for p in script.phrases] if script.phrases[0].start is not None else None
    fit = fit_timeline(raw_durations, video_duration, fixed_starts=fixed, max_tempo=ns.max_tempo)
    clips = []
    for i in range(len(script.phrases)):
        clip = work / f"fit_{i:03d}.wav"
        fit.durations[i] = round(_normalize(ffmpeg, work / f"norm_{i:03d}.wav", clip, fit.tempo), 3)
        clips.append(clip)
    assemble_track(clips, fit.starts, video_duration, outputs["audio"])

    cues = build_cues(script.phrases, fit, video_duration)
    outputs["srt"].write_text(build_srt(cues), encoding="utf-8")

    mux = [
        ffmpeg, "-n", "-hide_banner", "-loglevel", "error",
        "-i", str(video), "-i", str(outputs["audio"]),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        "-t", f"{video_duration:.3f}", "-movflags", "+faststart", str(outputs["video"]),
    ]
    _run(mux)
    if ns.burn_subtitles:
        style = (
            f"FontName={ns.subtitle_font},Fontsize={ns.subtitle_font_size},PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,BorderStyle=1,Outline=1.2,Shadow=0.6,Alignment=2,"
            f"MarginV={ns.subtitle_margin_v}"
        )
        vf = f"subtitles='{_filter_path(outputs['srt'])}':force_style='{style}'"
        _run([
            ffmpeg, "-n", "-hide_banner", "-loglevel", "error", "-i", str(outputs["video"]),
            "-vf", vf, "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "libx264", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "copy",
            "-movflags", "+faststart", str(outputs["burned"]),
        ])

    notes = {
        "created_at": datetime.now(UTC).isoformat(),
        "script": str(script_path),
        "script_sha256": _sha256(script_path),
        "source_video": str(video),
        "source_video_sha256": _sha256(video),
        "language": script.language,
        "market": ns.market,
        "category": ns.category,
        "approved_by": approved_by,
        "compliance": {"status": report.status, "rule_version": report.rule_version},
        "tts": {"backend": backend, "voice": voice, "speed": ns.speed, "tempo": fit.tempo},
        "video_duration": round(video_duration, 3),
        "voice_end": fit.voice_end,
        "fill_ratio": round(fit.voice_end / video_duration, 3),
        "warnings": fit.warnings + (["silent_backend_test_only"] if backend == "silent" else []),
        "cues": [asdict(c) for c in cues],
        "outputs": {k: str(v) for k, v in outputs.items()},
        "subtitles_burned": bool(ns.burn_subtitles),
    }
    outputs["notes"].write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    if not ns.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    return notes


def add_voiceover_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    parser = subparsers.add_parser("voiceover", help="TTS voiceover + SRT + AAC mux")
    nested = parser.add_subparsers(dest="voiceover_command", required=True)
    b = nested.add_parser("build")
    b.add_argument("--script", type=Path, required=True, help="approved localized script (.txt/.json)")
    b.add_argument("--video", type=Path, required=True, help="rendered video (e.g. showcase.mp4)")
    b.add_argument("--run-dir", type=Path, required=True)
    b.add_argument("--market", required=True)
    b.add_argument("--category", required=True)
    b.add_argument("--language", default="", help="es-MX / pt-BR / id-ID (default: from JSON or market)")
    b.add_argument("--approved-by", default="")
    b.add_argument("--backend", choices=BACKENDS, default="auto")
    b.add_argument("--voice", default="")
    b.add_argument("--speed", type=float, default=1.0)
    b.add_argument("--max-tempo", type=float, default=1.25)
    b.add_argument("--burn-subtitles", action="store_true")
    b.add_argument("--subtitle-font", default="Arial")
    b.add_argument("--subtitle-font-size", type=int, default=11)
    b.add_argument("--subtitle-margin-v", type=int, default=110,
                   help="libass units (PlayResY=288); 110 keeps text above the CTA/lower safe area")
    b.add_argument("--output-stem", default="")
    b.add_argument("--ai-generated", action="store_true")
    b.add_argument("--ai-label-enabled", action="store_true")
    b.add_argument("--keep-work", action="store_true")
    b.add_argument("--ffmpeg", default="")
    b.add_argument("--ffprobe", default="")


def handle_voiceover(ns: argparse.Namespace) -> int:
    if ns.voiceover_command != "build":
        return 2
    if not ns.language:
        try:
            ns.language = normalize_language(ns.market)
        except VoiceoverError:
            ns.language = ""
    try:
        notes = build_voiceover(ns)
    except (VoiceoverError, OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"status": "ok", **notes}, ensure_ascii=False, indent=2))
    return 0


__all__ = [
    "Cue", "FitResult", "Phrase", "VoiceScript", "VoiceoverError",
    "add_voiceover_parser", "build_cues", "build_srt", "fit_timeline", "format_srt_time",
    "handle_voiceover", "load_script", "normalize_language", "parse_script_text", "wrap_subtitle",
]
