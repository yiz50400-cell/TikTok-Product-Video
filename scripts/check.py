"""Run the frozen customer regression environment from any directory."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workflow.platforms.runtime import find_uv


def main():
    try:
        uv = find_uv(ROOT)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    return subprocess.run(
        [uv, "run", "--frozen", "--extra", "dev", "python", "-X", "utf8", "-m", "pytest", "-q", *sys.argv[1:]],
        cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
