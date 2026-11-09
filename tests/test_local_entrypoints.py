"""Command entrypoints must also work after an editable package install."""
from pathlib import Path
import os
import subprocess
import sys


def test_chatcut_health_help_from_foreign_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/chatcut_health.py"), "--help"],
        cwd=tmp_path, capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONPATH": str(root)},
    )
    assert result.returncode == 0, result.stderr
    assert "--timeout" in result.stdout
