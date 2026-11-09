# ChatCut 导出 → Remotion 包装 → 成片交付

Codex 统一管理任务。ChatCut 负责本地素材选镜头、动作连续性、节奏、裁切、转场与口播对齐；Remotion 在其导出的底片上统一制作标题、定时卖点卡、字幕和 CTA，输出 1080×1920 / 30 fps / H.264 / yuv420p MP4。支持按条制作，也支持 1–100 条顺序批处理与完整结果复用。

两者通过本地 MP4 与 SRT 交换，保留 ChatCut 项目 ID、原素材哈希和底片哈希。Remotion 不改变镜头顺序、不生成配音、不延长片尾，也不增加 BGM。ChatCut 底片为静音或仅口播，画面不烧入字幕；SRT 单独导出。已烧字幕的底片应回 ChatCut 重新导出，避免重复叠字。

## 安装

Python 环境按 [部署文档](../DEPLOYMENT.md) 安装。另安装 Node.js 22.13+（推荐 22 或 24 LTS），在项目根目录运行：

```sh
npm --prefix remotion ci
```

Remotion 及其配套包锁定相同版本。首次渲染可能下载 Chromium；也可通过 `REMOTION_BROWSER_EXECUTABLE` 指定已安装且兼容的 Chrome 可执行文件绝对路径。依赖与浏览器下载是工具安装，不是素材采集。正式商业使用按 Remotion 当前许可与团队规模办理。

## 制作和准备

1. 按 [本地剪辑流程](local-editing-workflow.md) 创建任务、导入原素材，取得真实 job_id、asset_id 和 SHA256。
2. Codex 通过 ChatCut MCP 创建/复制项目，完成镜头剪辑、节奏与配音同步。底片导出为 H.264/yuv420p/9:16 MP4，最长 180 秒；提供与底片完整时间线对应的 SRT。原始素材音轨应静音；口播版仅保留口播。
3. 从 [请求模板](../config/remotion-package.example.json) 复制到任务输出目录，填写真实字段。`base_subtitles_burned_in: false` 是操作者对底片的确认；程序不能识别画面是否已经烧字。卖点只写已核实商品事实，不能直接使用模板示例作为商品承诺。
4. 标题最多 80 字符、CTA 60 字符、单条字幕 110 字符；卖点卡最多 20 张，每张 80 字符，按 start/end 秒数排序且互不重叠。超长字幕应重新分句并保留同步时间，不自动删减口播。模板按实际字体测量自动换行并缩字号；标题最多4行、卡片3行、字幕4行、CTA2行，最小可读字号仍放不下时渲染失败并提示缩短文案，不截字。最终仍需查看实际排版。

```sh
uv run python scripts/package_remotion.py prepare --request /absolute/job/package-request.json --output /absolute/job/remotion-v1
uv run python scripts/package_remotion.py render --output /absolute/job/remotion-v1
```

Windows 可使用 `D:/任务/...` 绝对路径，命令参数相同。所有任务工具使用相同 `WORKFLOW_DATA_DIR`；默认项目 `.runtime`。准备阶段验证任务、素材归属、真实文件、音轨与字幕，复制底片到独立目录并锁定输入哈希。原文件不修改。

`remotion-v1` 保存 `prepared.json`、`props.json`、`media/base.mp4`、适用的 `subtitles.srt`。`rendered/` 保存成片、技术 QA、模板/底片血缘记录，以及待填写真实复核的交付清单模板。失败详情见 `render.log`。底片、字幕或模板发生变化时使用新的 `remotion-v2` 目录；已有成片不覆盖。

## 预览和精修

修改标题、卖点卡时间、颜色、CTA 后，用新请求和新目录重新准备。需要调整视觉模板时编辑 `remotion/src/Composition.tsx`；动态样式按帧计算，不使用 CSS 动画计时。

可在项目根目录启动 Studio（将路径换成已准备目录）：

```sh
npm --prefix remotion run studio -- --public-dir=/absolute/job/remotion-v1/media --props=/absolute/job/remotion-v1/props.json
```

画面裁切、镜头长短、转场和口播时机不合适时回 ChatCut 调整并重新导出。两边不是实时同步工程；Remotion 成片导回 ChatCut 后是合成视频，字幕与卡片不会还原为独立可编辑轨道。

## 批量与恢复

把多条完整请求组成 JSON 数组，顺序固定，每条任务+序号唯一：

```sh
uv run python scripts/package_remotion.py batch --request /absolute/job/batch.json --output /absolute/job/batch-v1
```

各条保存到 `item-001`、`item-002` 等目录，失败条目返回错误，其余继续。重试沿用同一个请求列表、顺序和输出目录；已完成条目核对输入、模板和输出哈希后复用。重新排序或更换输入应使用新批次目录。返回的 rendered_count 是技术渲染完成数，不代表已复核或已交付。

## 逐条复核与交付

完整观看包装后的最终视频：商品主体、动作连续性、字幕安全区/换行、卡片遮挡、开头/片尾、口播音质和同步。技术 QA 不替代这些观察。

复制 `rendered/delivery-manifest.template.json` 为单独的 `delivery-manifest.json`，填写实际 reviewer、含时区 reviewed_at 和具体 visual/listening 证据。模板默认 `passed: false`，未填写的模板不能登记成功。保留 render_record_path，用于校验最终 MP4、SRT 与原素材血缘。

```sh
uv run python scripts/deliver_video.py --job-id job_ACTUAL --ordinal 1 --manifest /absolute/job/delivery-manifest.json
```

交付登记成功才更新任务已交付数。交付包包含 MP4、适用 SRT、中文说明/文案及 `render-record.json`，后者关联 ChatCut 项目与 Remotion 模板版本。ChatCut 直接交付仍可使用原 `deliver_chatcut.py`；已有项目和旧脚本保持兼容。
