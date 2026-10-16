#!/usr/bin/env python3
"""Download accessible video URLs for product-video material collection.

Uses yt-dlp when available. Does not bypass login, CAPTCHA, payment gates, or account risk checks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_downloader() -> str | None:
    found = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    if found:
        return found
    script_path = Path(__file__).resolve()
    for parent in [Path.cwd(), *script_path.parents]:
        bundled = parent / ".tools" / "bin" / "yt-dlp.exe"
        if bundled.exists():
            return str(bundled)
    return None


def read_urls(values: list[str], urls_file: Path | None) -> list[str]:
    urls: list[str] = []
    if urls_file:
        for line in urls_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    urls.extend(v.strip() for v in values if v.strip())
    return list(dict.fromkeys(urls))


def main() -> int:
    parser = argparse.ArgumentParser(description="Download accessible product-video material URLs.")
    parser.add_argument("urls", nargs="*", help="Video/page URLs")
    parser.add_argument("--urls-file", type=Path, help="UTF-8 file with one URL per line")
    parser.add_argument("--output", required=True, type=Path, help="Output folder")
    parser.add_argument("--cookies-from-browser", choices=["chrome", "edge", "firefox"], help="Use employee's existing browser session when authorized")
    parser.add_argument("--max-downloads", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    yt_dlp = find_downloader()
    if not yt_dlp:
        print("ERROR: yt-dlp not found. Run bootstrap-video-editor-workspace.ps1 after confirmation.", file=sys.stderr)
        return 2

    urls = read_urls(args.urls, args.urls_file)
    if not urls:
        print("No URLs provided.")
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    failures = 0
    for idx, url in enumerate(urls[: args.max_downloads], 1):
        template = str(args.output / f"{idx:03d}_%(title).80s_%(id)s.%(ext)s")
        cmd = [
            yt_dlp,
            "--no-playlist",
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "-o",
            template,
            url,
        ]
        if args.cookies_from_browser:
            cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
        if args.dry_run:
            print("DRY_RUN " + " ".join(cmd))
            continue
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            print(f"OK {url}")
        else:
            failures += 1
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-8:]
            print(f"FAIL {url}\n" + "\n".join(tail), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
