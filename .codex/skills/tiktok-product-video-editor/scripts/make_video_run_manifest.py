#!/usr/bin/env python3
"""Create a small cache manifest for repeatable video edits."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a video-edit run manifest with cache keys.")
    parser.add_argument("--market", required=True)
    parser.add_argument("--voice", default="")
    parser.add_argument("--speed", default="")
    parser.add_argument("--script-file", required=True, type=Path)
    parser.add_argument("--clip", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    script_text = args.script_file.read_text(encoding="utf-8")
    script_hash = sha256_text(script_text)
    clip_items = [
        {
            "file": str(path),
            "sha256": sha256_file(path) if path.exists() else None,
            "exists": path.exists(),
        }
        for path in args.clip
    ]
    tts_key = sha256_text(
        json.dumps(
            {
                "market": args.market,
                "voice": args.voice,
                "speed": args.speed,
                "script_sha256": script_hash,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    render_key = sha256_text(
        json.dumps(
            {
                "market": args.market,
                "script_sha256": script_hash,
                "clips": clip_items,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    payload = {
        "schema_version": 1,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "market": args.market,
        "voice": args.voice,
        "speed": args.speed,
        "script_file": str(args.script_file),
        "script_sha256": script_hash,
        "tts_cache_key": tts_key,
        "render_cache_key": render_key,
        "clips": clip_items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
