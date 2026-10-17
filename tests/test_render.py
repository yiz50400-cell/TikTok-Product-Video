import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tk_ops_workspace.render import (
    DEFAULT_LAYOUT,
    RenderError,
    build_ffmpeg_args,
    build_filter_graph,
    fit_text,
    load_plan,
    merge_layout,
    parse_plan,
    render_showcase,
    resolve_fontfile,
    validate_against_source,
)

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _plan(**extra):
    return parse_plan({"segments": [{"start": 0, "end": 4, "speed": 2}, {"start": 5, "end": 8}],
                       "title": "Hola", "cta": "Compra", **extra})


def test_example_plan_loads_with_defaults():
    plan = load_plan(ROOT / "config" / "video-showcase.example.json")
    assert len(plan.segments) == 9
    assert plan.total_duration == pytest.approx(19.878, abs=0.001)
    assert plan.layout["arrow"] == DEFAULT_LAYOUT["arrow"]


def test_layout_overrides_and_rejects_unknown_keys():
    lay = merge_layout({"arrow": {"x": 10}, "fps": 25})
    assert lay["arrow"]["x"] == 10 and lay["arrow"]["y"] == 1245 and lay["fps"] == 25
    with pytest.raises(RenderError):
        merge_layout({"arow": {}})
    with pytest.raises(RenderError):
        merge_layout({"title": {"fontsize": 3}})


@pytest.mark.parametrize("seg", [{"start": 2, "end": 1}, {"start": -1, "end": 1},
                                 {"start": 0, "end": 1, "speed": 0}, {"end": 1}])
def test_invalid_segments(seg):
    with pytest.raises(RenderError):
        parse_plan({"segments": [seg]})


def test_segments_past_source_fail_before_render():
    plan = load_plan(ROOT / "config" / "video-showcase.example.json")
    with pytest.raises(RenderError, match="exceed the source"):
        validate_against_source(plan, 10.0)
    assert validate_against_source(plan, 36.0) == []


def test_overlap_and_short_segment_warnings():
    plan = parse_plan({"segments": [{"start": 0, "end": 4}, {"start": 3, "end": 3.2, "speed": 1}]})
    warnings = validate_against_source(plan, 10)
    assert "segment_1_overlaps_previous_segment" in warnings
    assert "segment_1_shorter_than_0.3s_after_speed" in warnings


def test_fit_text_keeps_short_title_and_wraps_long_one():
    block = DEFAULT_LAYOUT["title"]
    short = fit_text("Pasta Dental Probiótica", block, 1080, 18)
    assert short.lines == ("Pasta Dental Probiótica",) and short.font_size == 52
    long = fit_text("Pasta dental probiótica con extracto natural para toda la familia y más",
                    block, 1080, 18)
    assert 1 < len(long.lines) <= 2 and long.font_size <= 52 and not long.overflow
    huge = fit_text("palabra " * 60, block, 1080, 18)
    assert huge.overflow and huge.font_size == block["min_font_size"]


def test_fit_text_wraps_cjk_without_spaces():
    fitted = fit_text("这是一个非常非常长的中文标题需要自动换行显示才能放得下", DEFAULT_LAYOUT["title"], 1080, 18)
    assert len(fitted.lines) == 2


def test_filter_graph_default_matches_v020_layout():
    plan = _plan()
    title = fit_text(plan.title, plan.layout["title"], 1080, 18)
    cta = fit_text(plan.cta, plan.layout["cta"], 1080, 18)
    graph = build_filter_graph(plan, title=title, cta=cta, title_files=["title_0.txt"],
                               cta_files=["cta_0.txt"], fontfile="font.ttf")
    assert "trim=start=0:end=4,setpts=(PTS-STARTPTS)/2" in graph
    assert "concat=n=2:v=1:a=0[base]" in graph
    assert "textfile='title_0.txt':fontfile='font.ttf':enable='between(t,0,3)'" in graph
    assert "y=245:fontsize=52" in graph
    assert "enable='gte(t,2)'" in graph  # total 5s - 3s CTA
    assert "overlay=x=165:y='1245+42*sin(2*PI*t/0.72)'" in graph
    assert graph.rstrip().endswith("[u][ca]overlay=x=365:y=1320:enable='gte(t,2)'[v]")


def test_filter_graph_uses_layout_and_multiline_title():
    plan = _plan(layout={"title": {"y": 300}, "cart": {"x": 500, "y": 1000}})
    title = fit_text("x " * 40, plan.layout["title"], 1080, 18)
    graph = build_filter_graph(plan, title=title, cta=fit_text("c", plan.layout["cta"], 1080, 18),
                               title_files=[f"title_{i}.txt" for i in range(len(title.lines))],
                               cta_files=["cta_0.txt"], fontfile=None)
    assert "fontfile" not in graph
    assert "y=300:" in graph and f"y={300 + title.line_step}:" in graph
    assert "overlay=x=500:y=1000" in graph


def test_ffmpeg_args_never_overwrite():
    plan = _plan()
    args = build_ffmpeg_args("ffmpeg", plan, "G", Path("s.mp4"), Path("a.png"), Path("c.png"), Path("o.mp4"))
    assert "-n" in args and "-y" not in args
    assert args[args.index("-t") + 1] == "5"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"


def test_resolve_fontfile_explicit_missing_raises(tmp_path):
    with pytest.raises(RenderError):
        resolve_fontfile(str(tmp_path / "nope.ttf"), "", None)
    font = tmp_path / "f.ttf"
    font.write_bytes(b"x")
    assert resolve_fontfile(None, "f.ttf", tmp_path) == (font, [])


def _make_video(path: Path, seconds: float, src: str = "testsrc2") -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"{src}=s=1280x720:d={seconds}:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(path)], check=True)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg required")
def test_render_e2e_and_short_source_failure(tmp_path):
    src = tmp_path / "源 素材.mp4"
    _make_video(src, 9)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"title": "Título de prueba", "cta": "Pídelo",
                                "segments": [{"start": 0, "end": 4, "speed": 1.5},
                                             {"start": 4.5, "end": 8.5, "speed": 1.2}]}),
                    encoding="utf-8")
    result = render_showcase(source=src, run_dir=tmp_path / "run 1", segments_json=plan)
    assert result["qa"]["passed"], result["qa"]
    assert Path(result["qa"]["qa_json"]).is_file()
    with pytest.raises(RenderError, match="already exists"):
        render_showcase(source=src, run_dir=tmp_path / "run 1", segments_json=plan)
    short = tmp_path / "short.mp4"
    _make_video(short, 5)
    with pytest.raises(RenderError, match="exceed the source"):
        render_showcase(source=short, run_dir=tmp_path / "run 2", segments_json=plan)
    assert not (tmp_path / "run 2").exists()


def test_example_layout_section_equals_defaults():
    raw = json.loads((ROOT / "config" / "video-showcase.example.json").read_text(encoding="utf-8"))
    assert merge_layout(raw["layout"]) == DEFAULT_LAYOUT
