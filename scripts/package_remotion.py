#!/usr/bin/env python3
"""Package clean ChatCut exports with local Remotion graphics and captions."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow.remotion_bridge import load, prepare, render
from workflow.store import database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'render', 'batch'):
        p = sub.add_parser(command)
        if command in ('prepare', 'batch'):
            p.add_argument('--request', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = Path(os.environ.get('WORKFLOW_DATA_DIR', ROOT / '.runtime')).resolve()
    data.mkdir(parents=True, exist_ok=True)
    engine, sessions = database(data)
    try:
        if args.command == 'prepare':
            result = prepare(load(args.request), args.output, data, sessions)
        elif args.command == 'render':
            result = render(args.output, data, sessions)
        else:
            requests = load(args.request)
            if not isinstance(requests, list) or not 1 <= len(requests) <= 100:
                raise ValueError('批量请求须为1–100条JSON数组')
            ids = [(r.get('job_id'), r.get('ordinal')) for r in requests if isinstance(r, dict)]
            if len(ids) != len(requests) or len(set(ids)) != len(ids):
                raise ValueError('批量任务序号重复或格式错误')
            rows = []
            for request in requests:
                # prepare validates IDs before they can be used in filesystem paths.
                directory = args.output / ('item-' + str(len(rows) + 1).zfill(3))
                try:
                    prepare(request, directory, data, sessions)
                    result = render(directory, data, sessions)
                    rows.append({'ordinal': request['ordinal'], 'ok': True, 'output': str(directory.resolve()),
                                 'status': result['status']})
                except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                    rows.append({'ordinal': request.get('ordinal'), 'ok': False, 'error': str(exc)})
            result = {'items': rows, 'rendered_count': sum(r['ok'] for r in rows), 'delivered_count': 0}
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0 if all(r['ok'] for r in rows) else 1
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
