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
    encoding='utf-8')
    assert result.returncode == 0, result.stderr
    assert "--timeout" in result.stdout


def test_cooperative_commands_work_from_foreign_directory(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for script in ('package_remotion.py', 'deliver_video.py'):
        result = subprocess.run([sys.executable, str(root / 'scripts' / script), '--help'],
                                cwd=tmp_path, capture_output=True, text=True, encoding='utf-8')
        assert result.returncode == 0, result.stderr


def test_json_cli_survives_ascii_output_pipes(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'scripts/workflow.py'), 'create',
                             '--title', '中文商品', '--product', '收纳盒'],
                            cwd=tmp_path, capture_output=True, text=True, encoding='ascii',
                            env={**os.environ, 'PYTHONIOENCODING': 'ascii',
                                 'WORKFLOW_DATA_DIR': str(tmp_path / 'runtime')})
    assert result.returncode == 0, result.stderr
    import json
    assert json.loads(result.stdout)['title'] == '中文商品'
