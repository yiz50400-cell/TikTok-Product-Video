from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FFMPEG = Path(".tools/bin/ffmpeg.exe")
FFPROBE = Path(".tools/bin/ffprobe.exe")
W = 96
H = 170
FPS = 1


@dataclass
class FrameFeature:
    sec: int
    ahash: int
    dhash: int
    small: bytes
    mean: float


def run_json(cmd: list[str]) -> dict[str, Any]:
    p = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return json.loads(p.stdout)


def popcount(x: int) -> int:
    return x.bit_count()


def hamming(a: int, b: int) -> int:
    return popcount(a ^ b)


def ahash(gray: bytes, w: int, h: int) -> int:
    # 16x16 average hash over the already scaled gray frame.
    cells = 16
    cell_w = w / cells
    cell_h = h / cells
    vals: list[int] = []
    for cy in range(cells):
        y0 = int(cy * cell_h)
        y1 = max(y0 + 1, int((cy + 1) * cell_h))
        for cx in range(cells):
            x0 = int(cx * cell_w)
            x1 = max(x0 + 1, int((cx + 1) * cell_w))
            s = 0
            n = 0
            for y in range(y0, min(y1, h)):
                row = y * w
                for x in range(x0, min(x1, w)):
                    s += gray[row + x]
                    n += 1
            vals.append(s // max(1, n))
    avg = sum(vals) / len(vals)
    out = 0
    for v in vals:
        out = (out << 1) | (1 if v >= avg else 0)
    return out


def dhash(gray: bytes, w: int, h: int) -> int:
    # 16x16 difference hash using horizontal gradients.
    cells_x = 17
    cells_y = 16
    cell_w = w / cells_x
    cell_h = h / cells_y
    vals: list[int] = []
    for cy in range(cells_y):
        y0 = int(cy * cell_h)
        y1 = max(y0 + 1, int((cy + 1) * cell_h))
        for cx in range(cells_x):
            x0 = int(cx * cell_w)
            x1 = max(x0 + 1, int((cx + 1) * cell_w))
            s = 0
            n = 0
            for y in range(y0, min(y1, h)):
                row = y * w
                for x in range(x0, min(x1, w)):
                    s += gray[row + x]
                    n += 1
            vals.append(s // max(1, n))
    out = 0
    for y in range(cells_y):
        row = y * cells_x
        for x in range(cells_x - 1):
            out = (out << 1) | (1 if vals[row + x] > vals[row + x + 1] else 0)
    return out


def tiny_signature(gray: bytes, w: int, h: int) -> bytes:
    # 24x42 thumbnail used for mean absolute difference. Keep pure Python cheap.
    tw, th = 24, 42
    out = bytearray()
    for ty in range(th):
        y0 = int(ty * h / th)
        y1 = max(y0 + 1, int((ty + 1) * h / th))
        for tx in range(tw):
            x0 = int(tx * w / tw)
            x1 = max(x0 + 1, int((tx + 1) * w / tw))
            s = 0
            n = 0
            for y in range(y0, min(y1, h)):
                row = y * w
                for x in range(x0, min(x1, w)):
                    s += gray[row + x]
                    n += 1
            out.append(s // max(1, n))
    return bytes(out)


def mad(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def probe(path: Path) -> dict[str, Any]:
    data = run_json([
        str(FFPROBE),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ])
    fmt = data.get("format", {})
    vstreams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    astreams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    v = vstreams[0] if vstreams else {}
    return {
        "duration": float(fmt.get("duration") or v.get("duration") or 0),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "video_codec": v.get("codec_name", ""),
        "pix_fmt": v.get("pix_fmt", ""),
        "avg_frame_rate": v.get("avg_frame_rate", ""),
        "audio_codec": astreams[0].get("codec_name", "") if astreams else "",
    }


def features(path: Path) -> list[FrameFeature]:
    cmd = [
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
        "-an",
        "-pix_fmt",
        "gray",
        "-f",
        "rawvideo",
        "-",
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.stdout is not None
    frame_size = W * H
    out: list[FrameFeature] = []
    sec = 0
    while True:
        buf = p.stdout.read(frame_size)
        if not buf:
            break
        if len(buf) != frame_size:
            break
        small = tiny_signature(buf, W, H)
        out.append(FrameFeature(sec=sec, ahash=ahash(buf, W, H), dhash=dhash(buf, W, H), small=small, mean=sum(buf) / len(buf)))
        sec += 1
    _, err = p.communicate()
    if p.returncode != 0:
        raise RuntimeError(err.decode("utf-8", errors="replace").strip())
    return out


def consecutive_static_segments(frames: list[FrameFeature]) -> list[dict[str, Any]]:
    # A segment of 3 seconds means at least 4 one-second samples connected by 3 intervals.
    segments: list[dict[str, Any]] = []
    start: int | None = None
    diffs: list[float] = []
    hds: list[int] = []
    for i in range(1, len(frames)):
        d = mad(frames[i - 1].small, frames[i].small)
        hd = hamming(frames[i - 1].dhash, frames[i].dhash)
        similar = d <= 2.6 and hd <= 18
        if similar:
            if start is None:
                start = frames[i - 1].sec
                diffs = []
                hds = []
            diffs.append(d)
            hds.append(hd)
        else:
            if start is not None and frames[i - 1].sec - start >= 3:
                segments.append({
                    "start": start,
                    "end": frames[i - 1].sec,
                    "seconds": frames[i - 1].sec - start,
                    "avg_mad": round(sum(diffs) / len(diffs), 3),
                    "max_mad": round(max(diffs), 3),
                    "avg_dhash_hamming": round(sum(hds) / len(hds), 2),
                })
            start = None
            diffs = []
            hds = []
    if start is not None and frames[-1].sec - start >= 3:
        segments.append({
            "start": start,
            "end": frames[-1].sec,
            "seconds": frames[-1].sec - start,
            "avg_mad": round(sum(diffs) / len(diffs), 3),
            "max_mad": round(max(diffs), 3),
            "avg_dhash_hamming": round(sum(hds) / len(hds), 2),
        })
    return segments


def visually_near(a: FrameFeature, b: FrameFeature) -> bool:
    return mad(a.small, b.small) <= 3.2 and hamming(a.dhash, b.dhash) <= 22 and abs(a.mean - b.mean) <= 8


def cross_video_matches(items: list[dict[str, Any]], min_seconds: int = 3) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, int]] = set()
    for i in range(len(items)):
        fa = items[i]["features"]
        for j in range(i + 1, len(items)):
            fb = items[j]["features"]
            if not fa or not fb:
                continue
            # Bucket by ahash prefix to avoid checking every second against every second.
            buckets: dict[int, list[int]] = {}
            for bi, bf in enumerate(fb):
                buckets.setdefault(bf.ahash >> 224, []).append(bi)
            for ai, af in enumerate(fa):
                candidates = []
                for key in [(af.ahash >> 224), ((af.ahash >> 224) ^ 1), ((af.ahash >> 224) ^ 2), ((af.ahash >> 224) ^ 4)]:
                    candidates.extend(buckets.get(key, []))
                for bj in candidates:
                    if not visually_near(af, fb[bj]):
                        continue
                    k = 0
                    dsum = 0.0
                    while ai + k < len(fa) and bj + k < len(fb) and visually_near(fa[ai + k], fb[bj + k]):
                        dsum += mad(fa[ai + k].small, fb[bj + k].small)
                        k += 1
                    if k >= min_seconds:
                        key = (items[i]["name"], ai, items[j]["name"], bj)
                        if key not in seen:
                            seen.add(key)
                            matches.append({
                                "video_a": items[i]["name"],
                                "path_a": items[i]["path"],
                                "start_a": ai,
                                "end_a": ai + k - 1,
                                "video_b": items[j]["name"],
                                "path_b": items[j]["path"],
                                "start_b": bj,
                                "end_b": bj + k - 1,
                                "seconds": k,
                                "avg_mad": round(dsum / k, 3),
                            })
    # Merge obvious duplicates by keeping strongest long matches first.
    matches.sort(key=lambda x: (-x["seconds"], x["avg_mad"], x["video_a"], x["video_b"]))
    filtered: list[dict[str, Any]] = []
    occupied: set[tuple[str, int, str, int]] = set()
    for m in matches:
        sig = (m["video_a"], m["start_a"], m["video_b"], m["start_b"])
        if sig in occupied:
            continue
        filtered.append(m)
        if len(filtered) >= 500:
            break
    return filtered


def create_contact_sheet(video: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(FFMPEG),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        "fps=1,scale=180:-1,tile=6x5:margin=4:padding=2",
        "-frames:v",
        "1",
        "-y",
        str(out),
    ], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    videos: list[Path] = []
    for root in args.root:
        videos.extend(sorted(Path(root).rglob("*.mp4"), key=lambda p: str(p)))

    items: list[dict[str, Any]] = []
    for path in videos:
        info = probe(path)
        feats = features(path)
        static_segments = consecutive_static_segments(feats)
        rel = path.name
        parent = path.parent.name
        name = f"{parent}/{path.name}"
        item = {
            "name": name,
            "path": str(path),
            "probe": info,
            "frames_sampled": len(feats),
            "static_segments": static_segments,
            "features": feats,
        }
        items.append(item)
        if static_segments:
            safe = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
            create_contact_sheet(path, out_dir / "sheets" / f"{safe}_{rel}.jpg")

    cross = cross_video_matches(items)

    report_items = []
    for item in items:
        probe_info = item["probe"]
        vertical = probe_info["height"] > probe_info["width"] and abs((probe_info["width"] / probe_info["height"]) - (9 / 16)) < 0.08
        report_items.append({
            "name": item["name"],
            "path": item["path"],
            "duration": round(probe_info["duration"], 3),
            "width": probe_info["width"],
            "height": probe_info["height"],
            "video_codec": probe_info["video_codec"],
            "audio_codec": probe_info["audio_codec"],
            "pix_fmt": probe_info["pix_fmt"],
            "avg_frame_rate": probe_info["avg_frame_rate"],
            "vertical_9_16": vertical,
            "frames_sampled": item["frames_sampled"],
            "static_segments": item["static_segments"],
        })

    with (out_dir / "video_repetition_report.json").open("w", encoding="utf-8") as f:
        json.dump({"videos": report_items, "cross_video_matches": cross}, f, ensure_ascii=False, indent=2)

    with (out_dir / "video_summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "duration", "resolution", "codec", "audio", "pix_fmt", "vertical_9_16", "internal_3s_repeats"])
        for item in report_items:
            w.writerow([
                item["name"],
                item["duration"],
                f"{item['width']}x{item['height']}",
                item["video_codec"],
                item["audio_codec"],
                item["pix_fmt"],
                item["vertical_9_16"],
                "; ".join(f"{s['start']}-{s['end']}s({s['seconds']}s)" for s in item["static_segments"]),
            ])

    with (out_dir / "cross_video_matches.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["video_a", "range_a", "video_b", "range_b", "seconds", "avg_mad"])
        for m in cross:
            w.writerow([m["video_a"], f"{m['start_a']}-{m['end_a']}s", m["video_b"], f"{m['start_b']}-{m['end_b']}s", m["seconds"], m["avg_mad"]])

    print(json.dumps({
        "videos": len(report_items),
        "with_internal_3s_repeats": sum(1 for x in report_items if x["static_segments"]),
        "cross_video_3s_matches": len(cross),
        "output": str(out_dir),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
