# TikTok Product Video Editor · v0.4.0 ChatCut + Remotion 协同剪辑版

客户默认入口是 **Codex Desktop + ChatCut Desktop + Remotion**。提供本地素材、商品、市场、数量和风格，Codex 完成导入、分析筛选、策划、本地化口播、配音字幕、ChatCut 原生剪辑、底片导出、Remotion 字幕与视觉包装、逐条检查和本机交付。支持 MX、BR、ID、PH，任务数量 1–100。

> 使用本仓库 v0.4.0 完整源码或 Releases 中的 `TikTok-Product-Video-v0.4.0-chatcut-remotion.zip`。旧 v0.2.0 发布包不包含本次升级。历史记录 [SOURCE-VALIDATION.md](SOURCE-VALIDATION.md) 和 [VALIDATION.md](VALIDATION.md) 仅描述旧版验证，不代表本版或客户机器已验收。

先看 [部署与升级](DEPLOYMENT.md)，再看 [完整本地剪辑流程](docs/local-editing-workflow.md)。本次结果见 [升级验证记录](UPGRADE-VALIDATION.md)。

## 客户使用

安装 Python 3.12+、uv、FFmpeg/FFprobe 和 Node.js 22.13+，打开已登录的 ChatCut Desktop，把完整项目目录作为 Codex 工作区：

```sh
uv sync --frozen
npm --prefix remotion ci
```

edge-tts 随核心环境安装，可使用已配置的联网 TTS；可选本地 Kokoro：`uv sync --frozen --extra kokoro`（模型首次下载较大）。纯剪辑限制的是素材来源，不表示所有服务离线。

向 Codex 发一句话，例如：

> 用本机 D:/素材/收纳盒 的视频，为这个收纳盒做 3 条墨西哥商品展示片，真人演示风格，西语口播和字幕。

默认直接在已授权任务范围制作，不逐步索要稿件、音色或样片批准。只有明确要求「走对话精修」才逐步确认。审批与内部质量复核分别记录，不代签。

素材仅使用客户提供的本地文件和本地参考。缺少动作、角度或时长时保存进度并列出补料项，等待客户补充。所有成片无 BGM：静音或仅口播。通过 ChatCut MCP 编辑，不使用应用内 AI、`submit_*` 或界面自动化。

## 输出与验证

独立任务目录保存原片哈希、分析、策划、配音字幕、项目标识、实际导出和 QA 记录。交付 MP4、适用的独立 SRT、中文说明与复核证据；逐条登记已交付数，不覆盖客户原文件或已有成片。发布上传由客户自行处理。

默认流程是 **ChatCut 导出 → Remotion 包装 → 成片交付**。ChatCut 提供不烧字幕的底片与独立 SRT，Remotion 统一标题、卖点卡、字幕与 CTA；操作见[协同剪辑指南](docs/chatcut-remotion-workflow.md)。最终使用 `scripts/deliver_video.py` 验证并登记；ChatCut 直接交付也保留兼容。技术 QA 不能代替商品、动作连续性、画面文字与试听复核。

## 维护和兼容

- `remotion/`、`scripts/package_remotion.py`：本地包装模板、批量渲染与哈希复用。
- `.codex/skills/tiktok-product-video-editor/`：默认桌面剪辑操作规则。
- `.codex/skills/setup-video-editor-environment/`：本机环境检查。
- `workflow/`、`scripts/workflow.py`：任务与素材登记，以及显式调试/交互流水线；不是自动 ChatCut 渲染器。
- `src/tk_ops_workspace/` 和现有 PowerShell 渲染、配音、QA 工具：保留旧版兼容与排错。旧配音工具仍要求真实 `ApprovedBy`，不能为桌面默认流程虚构审批。
- `config/video-editor.example.yaml`：描述性偏好模板，不改变脚本行为；ChatCut MCP 样例见 `config/chatcut-mcp.*.example.toml`。

开发环境：`uv sync --frozen --extra dev` 与 `npm --prefix remotion ci`；检查 `uv run pytest -q`、`uv run ruff check .`、`npm --prefix remotion run lint`。设置 `REMOTION_SMOKE=1` 后运行 pytest 会额外执行真实浏览器渲染；CI 三平台均启用。维护者完成修改后运行 `uv run python scripts/generate_delivery_manifest.py` 更新交付清单，`--check` 校验。实际测试结果以本次验证记录为准；Windows 真机、在线 TTS 和真实商品批量画面验收须分别在客户环境完成，不能据单元测试宣称部署成功。

源码包不含客户素材、运行输出、账号、Cookie、Token 或密钥。客户使用自己的本机账号配置。
