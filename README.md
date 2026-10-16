# TikTok Product Video Editor

## 客户下载与部署

- [下载固定版本 v0.2.0 完整源码交付包](https://github.com/yiz50400-cell/TikTok-Product-Video-Editor-Delivery/releases/download/v0.2.0/TikTok-Product-Video-Editor-Delivery-v0.2.0.zip)
- [查看 v0.2.0 发布页](https://github.com/yiz50400-cell/TikTok-Product-Video-Editor-Delivery/releases/tag/v0.2.0)
- [中文安装说明](DEPLOYMENT.md)

这是公开的源码交付仓库，下载无需 GitHub 登录或邀请。下载 ZIP 后完整解压，在 Windows 10/11 电脑上按安装说明配置环境。项目包含可编辑的源码、Skill、剪辑脚本和资源；本地修改可用于排错和适配。普通访客没有向本仓库直接推送修改的权限。

交付源码基于员工电脑已验证的 v0.2.0 整理。员工原始验证记录见 [SOURCE-VALIDATION.md](SOURCE-VALIDATION.md)，本次交付整理检查见 [VALIDATION.md](VALIDATION.md)。

这是当前 Windows 工作区实际跑通的视频剪辑交付版本，基于 2026-10-16 使用的 Mexico/es-MX 商品展示剪辑链路整理。项目由 Codex Skill、PowerShell/Python 脚本、FFmpeg 工具链、合规检查和可复用的箭头/购物车叠加资源组成。

## 支持环境

- Windows 10/11
- Python 3.12+
- `uv` 0.8+，用于创建锁定 Python 环境
- FFmpeg/FFprobe 8.x，必须支持 H.264、PNG 叠加和 `yuv420p`
- 可选：Node.js 18+ 和 `yt-dlp`，用于素材查找与下载流程
- Codex Desktop，用于加载 `.codex/skills/tiktok-product-video-editor`

项目不上传 FFmpeg、Python、浏览器登录态、Cookie、Token、API Key 或任何店铺授权。接收者需要在自己的电脑上完成安装和登录。

## 下载和安装

在 GitHub 下载固定版本源码包后，在项目目录执行：

```powershell
uv sync --project .
```

如果没有 `uv`，从 Astral 官方渠道安装后再执行上面的命令。FFmpeg 建议使用当前 Windows 用户可用的 `Gyan.FFmpeg` 包，安装后确认：

```powershell
ffmpeg -version
ffprobe -version
```

也可以把 `ffmpeg.exe`、`ffprobe.exe` 和 `yt-dlp.exe` 放到项目的 `.tools\bin\`，该目录默认被诊断和渲染脚本优先使用。二进制文件被 `.gitignore` 排除，不随 GitHub 源码上传。

## 配置

先复制配置模板：

```powershell
Copy-Item .\config\video-editor.example.yaml .\config\video-editor.local.yaml
```

`video-editor.local.yaml` 只放本机路径和市场偏好，不要写密码、Cookie、Token 或 API Key。素材可以放在项目外任意目录；不要把客户素材复制回 Git 仓库。

视频 Skill 位于：

```text
.codex/skills/tiktok-product-video-editor/
```

## 启动和渲染

Codex 工作流入口是把本目录加入工作区，然后使用中文指令，例如：

```text
检查并补齐剪辑环境
```

当前实际使用的可复现渲染入口是：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\render-video-showcase.ps1 `
  -Source "D:\path\to\source.mp4" `
  -RunDir ".\outputs\video\mexico\2026-10-16\run-example" `
  -SegmentsJson ".\config\video-showcase.example.json"
```

渲染前仍必须按 Skill 展示并确认中文口播稿。该入口复现当前已跑通的画面展示逻辑：按片段裁剪、局部变速、竖屏 1080x1920、标题、购物车 CTA、红色下箭头和黄色购物车。当前版本不自动添加配音或字幕；如有配音需求，应按 Skill 的审批、合规和 SRT 时间轴规则扩展运行目录，不覆盖原始素材。

## 验证

只读环境诊断：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\doctor-video-editor-workspace.ps1
```

对成片做编码和尺寸检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify-video-delivery.ps1 `
  -Video ".\outputs\video\mexico\2026-10-16\run-example\showcase.mp4"
```

合规文本检查：

```powershell
uv run --project . tk-ops-workspace video-compliance check `
  --market Mexico `
  --category general `
  --script .\path\to\script.txt `
  --subtitles .\path\to\subtitles.txt `
  --onscreen-text .\path\to\onscreen.txt `
  --pdp .\path\to\pdp.txt
```

本次整理后在原电脑上实际验证了：源码和 Skill 文件可读、Python 测试可执行、视频 Skill 诊断脚本可执行、FFmpeg/FFprobe 可解析、用本机素材完成了一次独立运行目录渲染、成片为 H.264/1080x1920/yuv420p、输出未写回原素材目录。接收者仍需在自己的电脑上验证 FFmpeg 版本、素材可读性、目标市场文案和最终人工画面检查。

## 项目结构

- `.codex/skills/tiktok-product-video-editor/`：视频剪辑规则、合规参考和素材工具脚本。
- `scripts/render-video-showcase.ps1`：可移植的当前实际剪辑入口。
- `scripts/verify-video-delivery.ps1`：成片编码、尺寸、像素格式和时长检查。
- `scripts/doctor-video-editor-workspace.ps1`：只读环境诊断。
- `scripts/bootstrap-video-editor-workspace.ps1`：查看或应用剪辑依赖补齐计划。
- `assets/video/overlays/`：实际使用的红色下箭头和黄色购物车资源。
- `src/tk_ops_workspace/`：视频合规检查和工作区 CLI。
- `config/video-showcase.example.json`：当前剪辑片段配置示例。
- `DELIVERY-MANIFEST.json`：交付文件 SHA-256 清单。
- `outputs/video/`：运行时输出目录，默认不纳入 Git。

## 常见问题

**找不到 FFmpeg/FFprobe**  
确认命令在当前 Windows 用户 PATH 中，或放入 `.tools\bin\`，然后重新运行 `doctor-video-editor-workspace.ps1`。

**素材路径包含空格或中文**  
使用 PowerShell 参数传入完整路径并加双引号；不要把素材路径写死在脚本源码中。

**成片不是 1080x1920 或出现黑边**  
检查片段 JSON 和原素材比例，使用 `verify-video-delivery.ps1`，再人工抽帧确认主体是否被裁掉。

**标题或 CTA 乱码**  
确认 PowerShell 以 UTF-8 运行，脚本和 JSON 使用 UTF-8；不要把编辑器保存为本地代码页。

**合规检查被阻断**  
按 `.codex/skills/tiktok-product-video-editor/references/tiktok-shop-video-compliance.md` 修改口播、字幕、标签或画面文字，并重新执行检查。不要用未验证的数字、保证性、医疗性或促销性表述绕过检查。

**换电脑后 Codex 不加载 Skill**  
确认 Codex 工作区根目录就是本项目目录，并检查 `.codex/skills/tiktok-product-video-editor/SKILL.md` 存在。重新打开或新建 Codex 任务后再验收。

## 不随仓库交付的内容

原始视频、成片、SRT、运行日志、临时抽帧、客户数据、订单数据、本机账号配置、微信缓存路径、紫鸟配置、MCP OAuth 和任何密钥都不在本交付包中。接收者必须使用自己的素材、账号和授权。
