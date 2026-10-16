---
name: setup-video-editor-environment
description: Use when an employee asks in Chinese to检查并补齐剪辑环境, deploy, initialize, configure, diagnose, repair, or auto-complete the standalone TikTok product video editor workspace environment. Covers only video-editing dependencies such as bundled tools, uv/Python, FFmpeg/FFprobe, yt-dlp, and video-editor config; does not touch ads, Ziniao, shop reports, credentials, cookies, or tokens.
---

# Setup Video Editor Environment

## Rule

Use this skill only for the standalone product-video editing package. Keep it video-only.

Do not touch advertising, Ziniao, shop reports, image provider, cookies, tokens, account passwords, or unrelated project data.

## Flow

1. Confirm current folder is a video-editor package or employee workspace containing `.codex/skills/tiktok-product-video-editor`.
2. Run read-only plan:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-video-editor-workspace.ps1
   ```

3. Run read-only doctor:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor-video-editor-workspace.ps1
   ```

4. Show missing items, source, and local impact. Employee must explicitly confirm before install/config writes.
5. After confirmation, run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-video-editor-workspace.ps1 -Apply -Confirmed
   ```

6. Re-run doctor and report pass/fail by layer.

## What can be auto-completed after confirmation

- Use bundled `.tools\bin\ffmpeg.exe`, `.tools\bin\ffprobe.exe`, and `.tools\bin\yt-dlp.exe` when present.
- Install `uv` with winget only when missing.
- Install Python 3.12 runtime through `uv` only when missing.
- Install `Gyan.FFmpeg` with winget only when package tools and PATH tools are missing.
- Install `yt-dlp` with `uv tool install yt-dlp` only when package tools and PATH tools are missing.
- Create `config/video-editor.local.yaml` from `config/video-editor.example.yaml` only when missing.

## Acceptance

Environment is usable when:

- `doctor-video-editor-workspace.ps1` passes or only reports non-blocking config defaults;
- FFmpeg and FFprobe are available from bundled tools or PATH;
- yt-dlp is available from bundled tools or PATH;
- `probe_video_materials.py --help`, `prepare_video_assets.py --help`, and `download_material_urls.py --help` run;
- after voiceover approval, employee can render one H.264/AAC MP4 from their own material.

Do not claim final deployment until tested on the employee computer.
