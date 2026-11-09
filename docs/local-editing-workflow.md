# 本地素材到 ChatCut 交付

## 默认桌面制作

客户给出本地素材路径、商品信息、市场（MX/BR/ID/PH）、数量（1–100）和风格。Codex 在桌面会话内完成：

本地导入与哈希 → 分析筛选 → 逐条创意/镜头计划 → 本地化文案与内部复核 → 配音和字幕 → ChatCut 原生时间线 → 导出 → 技术与人工 QA → 登记交付。

没有足够素材时记录已完成数、待制作数与具体补料项，等待客户提供本地文件。不用 URL 代替原片，不恢复旧采集配置。本地参考可以分析，未提供参考时按已知商品事实创作。

默认在客户已授权的任务范围直接制作，不逐步要求审批；明确要求「走对话精修」时才展示中文稿、音色或风格收集反馈。内部审校与客户批准独立存储，不能代签。全片不加 BGM：静音或仅口播；原素材音轨静音。

ChatCut 先做 list_projects 只读连通，再新建/复制项目并明确 target_project。按当前 MCP 工具 schema 编辑、预览与导出，保留真实项目 ID。不用应用内 AI、submit_* 或 Computer Use。编辑器工具不可用时报告连接问题与真实进度。

## 任务工具（辅助登记与显式调试）

在项目根目录执行，返回的真实 job_id 用于后续命令。路径按本机实际位置替换，建议使用绝对路径；Windows PowerShell 支持相同参数。

```sh
uv run python scripts/workflow.py capabilities
uv run python scripts/workflow.py create --title "收纳盒三条" --product "收纳盒" --market MX --count 3 --style "真人演示"
uv run python scripts/workflow.py import job_ACTUAL /absolute/local/clip1.mp4 /absolute/local/clip2.mp4
```

`workflow.py run job_ACTUAL` 是可恢复的显式调试/交互流水线，可能要求真实稿件和审批证据；它不自动在 ChatCut 建时间线。不得把该命令作为桌面默认制作替代，更不能伪造审批以满足旧门禁。旧 `tk-ops-workspace render/voiceover/verify` 和 PowerShell 封装保留兼容排错，其输出不等于 ChatCut 项目。

## 原生导出登记

先完成实际 ChatCut 导出和逐条复核，再写本地 manifest。以下为结构示例，所有占位字段必须换成真实任务/素材/项目和观察，不能把示例视作已通过证据。数据目录默认项目 `.runtime`，自定义时各命令保持相同 `WORKFLOW_DATA_DIR`。

```json
{
  "project_id": "ACTUAL_CHATCUT_PROJECT_ID",
  "sources": [{"asset_id": "JOB_OWNED_ASSET_ID", "sha256": "ACTUAL_IMPORTED_SOURCE_SHA256"}],
  "video_path": "/absolute/export/final.mp4",
  "srt_path": "/absolute/export/final.es-MX.srt",
  "expected_duration": 20.0,
  "audio_mode": "narration",
  "delivery_explanation_zh": "填写本条创意、镜头安排和适用场景。",
  "delivery_text_zh": "填写本条中文交付说明。",
  "review": {
    "reviewer": "实际复核执行者",
    "reviewed_at": "2026-11-09T12:00:00+08:00",
    "visual": {"passed": true, "evidence": "填写实际逐条观看所得的商品、动作、文字和画面观察。"},
    "listening": {"passed": true, "evidence": "填写实际完整试听与字幕同步核对所得观察。"}
  }
}
```

```sh
uv run python scripts/deliver_chatcut.py --job-id job_ACTUAL --ordinal 1 --manifest /absolute/export/manifest.json
```

`ordinal` 是本条在任务中的序号。素材 ID 与 SHA256 必须属于该任务且与实际原片一致；视频与字幕使用本机绝对路径。`narration` 必须有真实 SRT 和试听复核；`silent` 必须无音轨，SRT 可省略，听觉复核不必伪造。

登记器检查真实文件、视频解码、H.264/yuv420p/9:16、时长、字幕与素材血缘，将交付文件和记录保存到任务交付目录并逐条更新完成数。默认制作按 1080x1920、目标帧率规划，并另外检查冻结帧、画面、字幕安全区和口播质量；不要把登记器通过当作全部创意质量验收。相同序号的不同成果拒绝覆盖，精确复用也校验交付文件。登记失败保留真实待办，不能宣称已经交付。

复核字段是调用者对真实复核的记录，不是客户批准。客户未逐步审批的正常桌面制作无需虚构批准记录。交付 MP4、适用的独立 SRT、中文说明和真实 QA/项目记录；回复使用实际文件的绝对路径链接。上传、挂商品和发布由客户手动处理。
