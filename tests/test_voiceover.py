import itertools
import json
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from tk_ops_workspace.voiceover import (
    Cue,
    Phrase,
    VoiceoverError,
    build_cues,
    build_srt,
    build_voiceover,
    fit_timeline,
    format_srt_time,
    normalize_language,
    parse_script_text,
    wrap_subtitle,
)


def test_parse_txt_skips_blank_and_comments():
    s = parse_script_text("# note\nHola\n\n  Mira esto  \n", suffix=".txt", language="Mexico")
    assert s.language == "es-MX"
    assert [p.text for p in s.phrases] == ["Hola", "Mira esto"]
    assert s.approved_by == ""


def test_parse_json_with_timings_and_approval():
    payload = {"language": "pt-BR", "approved_by": "IZ", "phrases": [
        {"text": "Olá", "start": 0.5, "end": 1.5}, {"text": "Compre já", "start": 2}]}
    s = parse_script_text(json.dumps(payload), suffix=".json")
    assert s.language == "pt-BR" and s.approved_by == "IZ"
    assert s.phrases[0] == Phrase("Olá", 0.5, 1.5)


@pytest.mark.parametrize("payload", [
    {"language": "es-MX", "phrases": []},
    {"language": "es-MX", "phrases": [{"text": "a", "start": 1}, {"text": "b"}]},
    {"language": "es-MX", "phrases": [{"text": "a", "start": 2}, {"text": "b", "start": 1}]},
    {"language": "fr-FR", "phrases": ["a"]},
    {"phrases": ["a"]},
])
def test_parse_json_rejects_invalid(payload):
    with pytest.raises(VoiceoverError):
        parse_script_text(json.dumps(payload), suffix=".json")


def test_normalize_language():
    assert normalize_language("id_id") == "id-ID"
    assert normalize_language("巴西") == "pt-BR"


def test_srt_time_format():
    assert format_srt_time(0) == "00:00:00,000"
    assert format_srt_time(3723.4567) == "01:02:03,457"


def test_build_srt():
    srt = build_srt([Cue(1, 0.3, 1.5, "Hola"), Cue(2, 1.6, 2.0, "Adiós")])
    assert srt == "1\n00:00:00,300 --> 00:00:01,500\nHola\n\n2\n00:00:01,600 --> 00:00:02,000\nAdiós\n"


def test_wrap_subtitle_balances_lines():
    assert wrap_subtitle("corto") == "corto"
    a, b = wrap_subtitle("Esta pasta dental deja tu sonrisa fresca todo el día").split("\n")
    assert abs(len(a) - len(b)) < 12


def test_fit_sequential_no_change():
    fit = fit_timeline([2.0, 2.0, 2.0], 7.5)
    assert fit.tempo == 1.0
    assert fit.starts[0] == 0.3
    assert fit.voice_end <= 7.2
    assert not [w for w in fit.warnings if "early" in w]


def test_fit_speeds_up_on_overrun():
    fit = fit_timeline([4.0, 4.0], 8.0)
    assert 1.0 < fit.tempo <= 1.25
    assert fit.voice_end <= 8.0 - 0.3 + 1e-6
    assert any("sped_up" in w for w in fit.warnings)


def test_fit_rejects_large_overrun():
    with pytest.raises(VoiceoverError):
        fit_timeline([10.0, 10.0], 8.0)


def test_fit_widens_gaps_and_warns_when_short():
    fit = fit_timeline([1.0, 1.0], 20.0)
    assert fit.starts[1] - fit.starts[0] - 1.0 == pytest.approx(0.6)
    assert any("ends_early" in w for w in fit.warnings)


def test_fit_fixed_starts():
    fit = fit_timeline([1.0, 1.2], 6.0, fixed_starts=[0.5, 3.0])
    assert fit.starts == [0.5, 3.0] and fit.tempo == 1.0
    fit = fit_timeline([3.0, 1.0], 6.0, fixed_starts=[0.5, 3.0])
    assert fit.tempo > 1.0


def test_cues_do_not_overlap():
    phrases = [Phrase("uno"), Phrase("dos"), Phrase("tres")]
    fit = fit_timeline([1.0, 1.0, 1.0], 4.0)
    cues = build_cues(phrases, fit, 4.0)
    for a, b in itertools.pairwise(cues):
        assert a.end < b.start


def _ns(tmp_path, video, script, **kw):
    base = {"script": script, "video": video, "run_dir": tmp_path / "run", "market": "Mexico",
                "category": "general", "language": "es-MX", "approved_by": "", "backend": "silent", "voice": "",
                "speed": 1.0, "max_tempo": 1.25, "burn_subtitles": False, "subtitle_font": "Arial",
                "subtitle_font_size": 11, "subtitle_margin_v": 110, "output_stem": "", "ai_generated": False,
                "ai_label_enabled": False, "keep_work": False, "ffmpeg": "", "ffprobe": ""}
    base.update(kw)
    return Namespace(**base)


def test_approval_gate_blocks_before_any_output(tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("Hola\n", encoding="utf-8")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(VoiceoverError, match="approval"):
        build_voiceover(_ns(tmp_path, video, script))
    assert not (tmp_path / "run").exists()


def test_compliance_gate_blocks(tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("El mejor producto, 100% natural y garantizado\n", encoding="utf-8")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    with pytest.raises(VoiceoverError, match="compliance"):
        build_voiceover(_ns(tmp_path, video, script, approved_by="IZ"))


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg")
def test_end_to_end_silent_backend(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=1080x1920:d=6:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(video)], check=True)
    script = tmp_path / "s.txt"
    script.write_text("Mira esta pasta dental\nTu sonrisa más fresca\nPídela en el carrito\n",
                      encoding="utf-8")
    ns = _ns(tmp_path, video, script, approved_by="IZ", burn_subtitles=True)
    notes = build_voiceover(ns)
    out = Path(notes["outputs"]["burned"])
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt",
         "-of", "json", str(out)], capture_output=True, text=True, check=True).stdout)
    kinds = {s["codec_type"]: s for s in probe["streams"]}
    assert kinds["audio"]["codec_name"] == "aac" and kinds["video"]["pix_fmt"] == "yuv420p"
    assert Path(notes["outputs"]["srt"]).read_text(encoding="utf-8").startswith("1\n00:00:00,300")
    assert notes["tts"]["backend"] == "silent"
    with pytest.raises(VoiceoverError, match="overwrite"):
        build_voiceover(ns)
