#!/usr/bin/env python3
"""Generate or check DELIVERY-MANIFEST.json from git-tracked files. VERSION is the single source.

    uv run python scripts/generate_delivery_manifest.py          # rewrite manifest
    uv run python scripts/generate_delivery_manifest.py --check  # CI: fail if stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "DELIVERY-MANIFEST.json"
EXCLUDE = {MANIFEST}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout.decode("utf-8")
    return sorted(p for p in out.split("\0") if p and p not in EXCLUDE and (ROOT / p).is_file())


def read_version() -> str:
    raw = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return raw if raw.startswith("v") else f"v{raw}"


def build() -> dict[str, object]:
    files = []
    for rel in tracked_files():
        data = (ROOT / rel).read_bytes()
        files.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return {"version": read_version(), "files": files}


def render(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render(build())
    path = ROOT / MANIFEST
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != expected:
            print("DELIVERY-MANIFEST.json is stale; run scripts/generate_delivery_manifest.py")
            return 1
        print("DELIVERY-MANIFEST.json is up to date")
        return 0
    path.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {MANIFEST} ({read_version()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
