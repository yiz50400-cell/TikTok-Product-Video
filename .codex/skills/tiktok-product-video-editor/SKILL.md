---
name: tiktok-product-video-editor
description: Edit customer-supplied local product footage using Codex Desktop and ChatCut Desktop. Use for TikTok product editing, local clip analysis, multi-market scripts, narration, captions, native editing, export, QA and MP4/SRT delivery.
---

# 本地商品视频剪辑

客户默认入口为 Codex Desktop + 已登录的 ChatCut Desktop。先读项目 README、DEPLOYMENT 和 docs/local-editing-workflow.md。支持市场 MX/es-MX、BR/pt-BR、ID/id-ID、PH（任务语言按客户需求确定），数量 1–100。

## 执行合同

只用客户明确提供的本地视频和本地参考；商品链接或图片不能替代视频素材。不搜索、下载视频或安装采集组件。缺料列明缺少的商品动作、角度、场景/时长，保存已完成进度并等待本地补充。

默认直接完成已授权制作，不逐步要求中文稿、音色或样片批准；客户明确要求「走对话精修」才逐步确认。内部审校不是客户审批，不虚构批准人、批准文本或试听证据。不擅自创建后台任务或代理。

所有成片无 BGM：无口播则所有素材静音，有口播则仅口播轨。剪辑只走 ChatCut MCP；禁用应用内 AI、submit_* 生成和界面自动化。配音使用本机已配置 TTS；纯剪辑不等于服务离线。

## 顺序

1. 核对本地路径、商品、市场、数量、风格；能从上下文确定则沿用。先导入素材并绑定真实 SHA256，保留原片。
2. 检查每段可用镜头、商品一致性、清晰度、水印、连续动作起止和实际时长；为 hook、展示、动作、结果、CTA 选择合适片段，不强制把每段都塞入成片。
3. 制定逐条镜头计划、去重差异和时长，口播只写可证实的卖点；参考 references/tiktok-shop-video-compliance.md。自行内部校对中文稿与目标语言，只有对话精修才向客户逐步确认。
4. 准备口播音频和对应 SRT；检查当地语言、音色、时长、停顿和同步。缩短超长稿，不以冻结画面补时。静音版无需伪造口播字幕。
5. ChatCut MCP 先用 list_projects 只读确认连通；新建项目或复制已有项目，明确 target_project。用当前工具 schema 导入本地媒体、编辑时间线/字幕/转场/原生效果，保留项目 ID。不要覆盖客户同名项目。
6. 预览确认商品动作连续、主体裁切、字幕可读与安全区，核对所有原素材音轨静音。导出实际 MP4，记录项目与路径；导出完成前不报告成片。
7. 独立检查 H.264、1080x1920、yuv420p、目标帧率、计划时长、冻结帧和音轨。逐条人工视觉复核；口播版逐条试听并核对字幕，不把技术 QA 当视觉验收。
8. 使用 scripts/deliver_chatcut.py 登记真实成片、素材归属、字幕、中文说明与复核证据，按真实成功条数更新进度。失败保留证据和待办，成功文件不覆盖。交付可点击的本机绝对路径。

## 兼容与恢复

scripts/workflow.py 用于任务创建、导入、分析/计划登记；run 为显式调试/交互流水线，可能要求真实审批，不是自动 ChatCut 渲染入口。旧 tk-ops-workspace FFmpeg 工具保留调试兼容，不冒充原生 ChatCut 项目。断点续作先核对素材哈希和已交付 ordinal，不重算或覆盖已验证成果。发布上传由客户手动完成。
