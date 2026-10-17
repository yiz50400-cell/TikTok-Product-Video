import json

from tk_ops_workspace.cli import build_parser, main


def test_subcommands_present_and_removed_ones_gone():
    choices = build_parser()._subparsers._group_actions[0].choices
    assert {"doctor", "video-compliance", "voiceover", "render", "verify"} <= set(choices)
    assert "build-release" not in choices and "jimeng-prompt" not in choices


def test_render_plan_only_prints_graph(capsys):
    assert main(["render", "showcase", "--source", "x", "--run-dir", "y", "--plan-only"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["duration_seconds"] > 0 and "concat=n=9" in payload["graph"]


def test_package_version_comes_from_version_file():
    from importlib.metadata import version
    from pathlib import Path

    raw = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
    assert version("tiktok-product-video") == raw.lstrip("v")
