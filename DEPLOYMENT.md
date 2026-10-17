# Windows 客户部署

## 下载

从本仓库 Releases 下载 TikTok-Product-Video-Editor-Delivery-v0.2.0.zip，完整解压到一个独立目录，例如 D:\TikTokVideoEditor。保留 .codex、src、scripts、assets、config 等目录结构。

## 配置环境

本项目使用 Windows 10/11、Python 3.12+、uv、FFmpeg 和 FFprobe。素材下载流程另外需要 yt-dlp。

在解压后的项目目录打开 PowerShell，执行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-video-editor-workspace.ps1
~~~

核对安装计划后，如需自动补齐环境，执行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-video-editor-workspace.ps1 -Apply -Confirmed
uv sync --frozen --project .
# 需要配音时二选一或都装（Kokoro 体积大，首次运行会下载模型）：
# uv sync --frozen --project . --extra kokoro
# uv sync --frozen --project . --extra edge-tts
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor-video-editor-workspace.ps1
~~~

如需手工创建本机配置，且该文件尚不存在：

~~~powershell
Copy-Item .\config\video-editor.example.yaml .\config\video-editor.local.yaml
~~~

## 使用和验收

将完整项目目录作为 Codex 工作区，按 .codex/skills/setup-video-editor-environment/SKILL.md 检查环境，按 .codex/skills/tiktok-product-video-editor/SKILL.md 执行剪辑。可先发送：

> 请读取本项目 README 和剪辑环境 Skill，检查并补齐这台电脑的剪辑环境。

使用客户自己的素材，按 README 的渲染示例生成一个视频，并执行 scripts/verify-video-delivery.ps1，再检查播放、画面和文字。不带 -VoiceoverScript 时固定渲染脚本输出无音频的画面展示版本；带 -VoiceoverScript（需已审批、合规通过）时会额外输出 .voiced.mp4 和 .srt，用 `verify-video-delivery.ps1 -RequireAudio` 检查音轨，并人工试听配音、核对字幕位置和时间轴。也可在 bootstrap 时加 `-WithTts kokoro|edge-tts|all` 安装配音依赖。

## 本地维护

需要排错时，在这台电脑上保留完整项目目录和错误信息，由维护者使用 Codex 修改本地源码。更换交付版本前保留本地修改和配置的备份。

客户使用自己的素材、账号和本机配置。完整文件清单及校验值见 DELIVERY-MANIFEST.json。
