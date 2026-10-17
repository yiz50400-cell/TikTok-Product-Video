import shutil
import subprocess

import pytest

from tk_ops_workspace.media import parse_rate
from tk_ops_workspace.qa import QaSettings, evaluate, parse_freezes, run_qa, unique_report_path

GOOD = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920,
         "pix_fmt": "yuv420p", "r_frame_rate": "30/1", "avg_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "20.0"},
}


def test_parse_rate():
    assert parse_rate("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert parse_rate("0/0") is None and parse_rate("") is None


def test_parse_freezes_closes_open_freeze_at_end():
    log = ("[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 1.5\n"
           "[freezedetect @ 0x1] lavfi.freezedetect.freeze_duration: 1.2\n"
           "[freezedetect @ 0x1] lavfi.freezedetect.freeze_end: 2.7\n"
           "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 5.966667\n")
    freezes = parse_freezes(log, 19.8)
    assert freezes[0] == {"start": 1.5, "duration": 1.2, "end": 2.7}
    assert freezes[1]["end"] == 19.8 and freezes[1]["duration"] == pytest.approx(13.833, abs=0.01)


def test_evaluate_good_passes():
    result = evaluate(GOOD, QaSettings(expected_duration=20.1, require_audio=True), [])
    assert result["passed"], result["errors"]


def test_evaluate_reports_each_problem():
    bad = {"streams": [{"codec_type": "video", "codec_name": "hevc", "width": 720, "height": 1280,
                        "pix_fmt": "yuv444p", "avg_frame_rate": "25/1"}],
           "format": {"duration": "10"}}
    result = evaluate(bad, QaSettings(expected_duration=20, require_audio=True),
                      [{"start": 1, "end": 3, "duration": 2}])
    assert set(result["errors"]) == {"missing_h264_video_stream", "expected_1080x1920",
                                     "expected_yuv420p", "expected_fps_30", "duration_mismatch",
                                     "missing_audio_stream", "freeze_detected"}


def test_evaluate_short_freeze_ok_and_fps_optional():
    result = evaluate(GOOD, QaSettings(expected_fps=None), [{"start": 1, "end": 1.5, "duration": 0.5}])
    assert result["passed"]
    assert "freeze_check_not_run" in evaluate(GOOD, QaSettings())["warnings"]


def test_unique_report_path_never_overwrites(tmp_path):
    video = tmp_path / "a.mp4"
    first = unique_report_path(video)
    first.write_text("{}")
    assert unique_report_path(video) != first


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg")
def test_run_qa_detects_frozen_video(tmp_path):
    video = tmp_path / "frozen.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=gray:s=1080x1920:d=3:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(video)], check=True)
    result = run_qa(video, QaSettings(expected_duration=3))
    assert "freeze_detected" in result["errors"]
    assert (tmp_path / "frozen.qa.json").is_file()
