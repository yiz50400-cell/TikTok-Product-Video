---
name: setup-video-editor-environment
description: Check, deploy and repair the local-footage Codex Desktop plus ChatCut Desktop product editing environment on macOS or Windows, including Python, uv, FFmpeg, locked dependencies and MCP connectivity.
---

# 本地剪辑环境

先读 README.md 和 DEPLOYMENT.md。保护已有素材、配置和账号，使用客户自己的 Codex/ChatCut 登录；不复制全局 auth/config，不部署视频采集组件。

1. 识别操作系统与项目目录，检查 Python 3.12+、uv、FFmpeg/FFprobe。Windows 可运行 scripts/doctor-video-editor-workspace.ps1 和不带 -Apply 的 bootstrap 查看现状。
2. 用户已要求部署/补齐时执行所需安装，不重复索要逐步批准。Windows bootstrap 应用参数为 -Apply -Confirmed；macOS 使用本机已有包管理器。不要把 Windows 二进制放到 macOS。
3. 项目根目录 `uv sync --frozen`；edge-tts 包含在核心依赖。仅需要本地 Kokoro 时加 --extra kokoro；开发加 --extra dev。首次模型下载单独报告。
4. 本地配置不存在才从 config/video-editor.example.yaml 创建，保留原配置；该 YAML 只描述偏好，不是脚本参数。
5. 打开已登录的 ChatCut Desktop，优先复用已接通的 MCP。手动配置参考 config/chatcut-mcp.*.example.toml，使用本机真实绝对路径，不整体覆盖全局配置。
6. 以 list_projects 只读调用确认 ChatCut 实际响应；进程存在不算连通。失败报告原始错误，不回退应用内 AI、submit_* 或 Computer Use。Windows 手动重启。
7. 使用客户本地素材跑一次 ChatCut 编辑、导出与 deliver_chatcut 登记，再检查画面/字幕/口播和技术 QA。只报告实际通过的层次；依赖安装、只读连通、技术样片和客户质量验收分别记录。

旧 PowerShell/FFmpeg 工具保留历史兼容，旧配音步骤仍需真实审批记录。客户桌面默认制作无需逐步审稿；不要为兼容工具编造批准人。
