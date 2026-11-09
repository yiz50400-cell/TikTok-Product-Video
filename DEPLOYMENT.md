# macOS / Windows 客户部署与升级

从本仓库 Releases 获取 `TikTok-Product-Video-v0.4.0-chatcut-remotion.zip`，或使用 v0.4.0 完整源码目录，不以历史 v0.2.0 压缩包代替。保留 `.codex`、`workflow`、`src`、`scripts`、`config`、`assets`、`remotion`、`pyproject.toml` 和 `uv.lock`。

## 环境

两平台均需要 Codex Desktop、已登录并打开的 ChatCut Desktop、Python 3.12+、uv、FFmpeg/FFprobe 和 Node.js 22.13+（推荐 22/24 LTS）。客户使用自己的登录与凭据；不要复制他人的全局 Codex `auth.json`、`config.toml` 或密钥。

macOS：用现有包管理器安装 uv 与 FFmpeg；旧版文字渲染依赖 drawtext/subtitles 滤镜，Homebrew 请安装 ffmpeg-full 并将其 bin 加入 PATH，确认当前终端能找到命令；不把 Windows `.exe` 路径套用到 macOS。

Windows 10/11：在项目目录打开 PowerShell。可先查看只读安装计划和诊断：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap-video-editor-workspace.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor-video-editor-workspace.ps1
```

用户已要求补齐环境时可执行 `bootstrap-video-editor-workspace.ps1 -Apply -Confirmed`。FFmpeg/FFprobe 可位于当前用户 PATH 或项目 `.tools/bin/`，不随源码包提供。

两平台在项目目录执行：

```sh
uv sync --frozen
npm --prefix remotion ci
ffmpeg -version
ffprobe -version
uv run python scripts/workflow.py capabilities
```

edge-tts 已包含在核心安装中，联网服务仍须客户本机可达。需要本地 Kokoro 时执行 `uv sync --frozen --extra kokoro`；开发检查使用 `--extra dev`。不要为剪辑部署素材采集组件。

## 配置 ChatCut

在 Codex 打开完整项目目录，读取项目剪辑 Skill。优先使用当前已接通的 ChatCut Desktop MCP。需要手动接入时参考 `config/chatcut-mcp.macos.example.toml` 或 `config/chatcut-mcp.windows.example.toml`，把 command 改成本机真实可执行文件绝对路径；样例不是可直接复制覆盖全局配置的文件，也不会自动展开占位符。

通过 `list_projects` 等只读调用确认 MCP 有实际响应；进程存在不等于健康。失败时保留错误、修复连接，不绕到应用内 AI 或界面操作。Windows 需用户手动保持/重启 ChatCut。

`config/video-editor.local.yaml` 不存在时才从 example 复制。该模板仅描述偏好，不是运行参数；保留已有配置，真实密钥不写入项目。

## 客户机器验收

1. 验证锁定依赖安装、FFmpeg/FFprobe 和 ChatCut MCP 只读连通。
2. 使用客户本地素材创建一个任务，经 ChatCut 导入、剪辑、导出干净底片，再按[协同指南](docs/chatcut-remotion-workflow.md)用 Remotion 包装并登记最终 MP4 与字幕。
3. 检查编码、尺寸、帧率、时长、冻结帧；人工看画面/商品/字幕安全区并试听。验证交付数量和恢复记录。
4. 逐项报告实际结果。只完成依赖安装或合成视频测试时，不宣称客户部署或真实批量质量验收成功。

## 升级和回滚

关闭正在写入该项目的任务，记录未交付数量。先把旧项目完整复制到独立备份目录，保留原始素材位置、客户本地配置、运行数据库、输出与本地修改。新版本解压到并列目录，重新 `uv sync --frozen`；按新模板逐项迁移需要的本地路径，核对后才继续任务。不要把旧版采集配置并入新任务。

首次验收使用独立输出目录与备份后的运行状态，不覆盖旧成果。失败时停止新任务，切回旧目录及与它匹配的备份数据库/配置；保留新版本日志供排错，不把新旧状态文件盲目混用。全局账号凭据不属于项目升级迁移内容。

详细制作和导出登记见 [本地剪辑流程](docs/local-editing-workflow.md)。

Remotion 首次渲染可能下载 Chromium，已有兼容 Chrome 可用 REMOTION_BROWSER_EXECUTABLE 指定。工具安装与 TTS 可能联网，素材始终只用本地文件。商业部署核对 Remotion 当前许可及团队规模。
