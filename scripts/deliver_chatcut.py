#!/usr/bin/env python3
"""Register an actual local ChatCut export against an existing workflow job."""
import argparse
import json
import os
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow.desktop_delivery import local_file, register_delivery  # noqa: E402
from workflow.store import database  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--ordinal', required=True, type=int)
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    data = Path(os.environ.get('WORKFLOW_DATA_DIR', ROOT / '.runtime')).resolve()
    data.mkdir(parents=True, exist_ok=True)
    engine, sessions = database(data)
    try:
        manifest = json.loads(local_file(args.manifest, '.json').read_text(encoding='utf-8'))
        result = register_delivery(data, sessions, args.job_id, args.ordinal, manifest)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f'交付登记失败: {exc}\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
