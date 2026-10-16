# 交付验证记录

验证日期：2026-10-16  
验证目录：本交付目录，不是原工作区目录

## 已实际验证

- `uv sync --project . --extra dev`：成功，使用 Python 3.12.13。
- `pytest -q`：成功，9 passed。
- `doctor-video-editor-workspace.ps1 -Config config/video-editor.example.yaml`：成功，`uv`、Python、FFmpeg、FFprobe、yt-dlp 均可用。
- `bootstrap-video-editor-workspace.ps1`：以只读 plan 模式执行成功；仅提示尚未创建本机 `video-editor.local.yaml`，没有执行安装或外部写入。
- `render-video-showcase.ps1`：使用本机素材完成独立运行目录渲染，9 段片段，输出约 19.9 秒。
- `verify-video-delivery.ps1`：通过，H.264、1080x1920、30fps、yuv420p。
- 已抽取开头和 CTA 尾段画面检查，标题、CTA、红色下箭头和黄色购物车可见。
- 已生成 `DELIVERY-MANIFEST.json`，记录交付源码文件 SHA-256 和大小。

## 本机工具版本

- FFmpeg/FFprobe：`N-125978-g95c43d7df7-20260806`
- `uv`：`0.11.31`
- Python：`3.12.13`
- `yt-dlp`：`2026.07.04`

## 未作为通过条件的项目

- 未在交付目录生成配音、SRT 或字幕烧录版本；当前实际跑通版本是无音频的画面展示成片。
- 未使用接收者账号、素材、TikTok Shop、紫鸟或 MCP 授权；这些必须在新电脑单独配置。
- `ruff check src tests` 发现原工作区既有的 19 个代码风格/时区告警。本次没有修改无关业务源码；单元测试和实际视频链路均已通过。
- FFmpeg 渲染时出现 Fontconfig 配置缺失警告，但输出成功、文字可见；Windows 接收者如遇字体差异，应在本机确认字体和文字位置。
