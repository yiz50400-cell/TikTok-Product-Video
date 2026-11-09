# v0.3.0 纯剪辑版升级验证

验证日期：2026-11-09（Asia/Shanghai）。以下记录发布前的本机验证；远程构建结果以该发布提交对应的 GitHub Actions 记录为准。

## 来源和范围

- 客户仓库基线：TikTok-Product-Video `dd31351f13017a57b3eeec48984207952aee40c1`。
- 工作流来源：tiktok-video-workflow `c371cf3c87325861df2c6ff735f7b87b8aea5c33`。
- 工作分支：`codex/local-material-editing`。
- 原文件完整备份：本地 `.git/migration-backups/customer-before-upgrade.tar`；逐文件修改备份亦在 `.git/migration-backups/`。这些维护记录不进入交付包。
- 完整版工作流未修改；原有 `_scratch/` 未跟踪目录保持原状。

## 已完成

客户默认从本地素材开始，由 Codex Desktop + ChatCut 完成批量剪辑、配音、字幕与逐条交付。迁入本地任务、分析、混剪、声音/字幕准备、连续动作检查、失败恢复、哈希证据及本机交付模块；原有 FFmpeg/配音兼容工具仍保留。

客户版不含 collection/unattended 采集器、网络视频下载脚本、采集依赖或 Docker/Evil 安装流程。API/CLI/MCP 拒绝网址素材和 collection 输入，旧任务携带采集配置也在执行前被拒绝。缺料请求本地补充；部分交付后继续导入本地素材和分析不会重置已交付记录。

ChatCut 实际导出可通过 `scripts/deliver_chatcut.py` 登记，校验真实 MP4、源素材归属及哈希、SRT 时序、音轨模式、完整解码与真实复核记录。不可变交付包包含视频、适用字幕、中文说明、中文文案和证据清单；每次复用核对已交付文件及素材，进度按实际条目计算。内部技术/视觉复核不冒充客户审批。

安装统一使用 `pyproject.toml` + `uv.lock`，Python 3.12+。本次选择 3.12；客户无需部署采集服务。CI 配置覆盖 Windows、Linux、macOS；远程 CI 尚未运行。

## 实际验证结果

在 macOS ARM64、Python 3.12.14、冻结依赖环境完成：

| 检查 | 结果 |
| --- | --- |
| `uv sync --frozen --extra dev --offline`（依赖首次安装后复验） | 通过，52 个包 |
| `PATH="<项目>/.tools/bin:$PATH" .venv/bin/python -m pytest -q -ra` | **459 passed, 3 skipped，79.37 秒** |
| `.venv/bin/ruff check .` | 通过 |
| `git diff --check` | 通过 |
| ChatCut MCP `list_projects` 只读探针 | 成功返回本机项目目录；未修改既有项目 |
| CLI capabilities、原生交付命令、独立 health help | 可执行；capabilities 版本 0.3.0，本地素材模式 |
| MCP 样例 TOML、CI YAML、客户文档相对链接 | 解析/核对通过 |
| 独立代码复核 | 两项交付校验问题修复后复核通过 |

测试使用真实本地合成视频，覆盖本地导入与去重、单源/多源链路、损坏文件、失败恢复、字幕与声音准备、原生时间线编译、成片交付、精确复用、部分批次补料和旧版渲染兼容。网络配音使用可控测试替身，未在该次验证请求真实 TTS。

为了运行旧版 FFmpeg/FFprobe 回归，测试机在忽略目录 `.tools/bin` 使用已安装 imageio-ffmpeg 的 FFmpeg 和经过 npm 包 integrity 校验的 macOS ARM64 FFprobe。二进制、测试产物、账号与客户素材均不进入源码提交。

## 未验收的范围

- 3 个跳过用例需要真实 Windows 退出码/Job Object；不能据 macOS 结果宣称 Windows 真机部署已通过。
- 可选 LaMa/OpenCV/Torch 修补引擎的两个测试文件不在默认轻量回归中；它们保留独立依赖，未安装/运行大模型。
- 未使用真实客户商品素材制作本次批量成片，未验证在线 TTS 服务可达性；ChatCut 只做连通检查，未运行完整真实项目导出。
- 技术测试不代表真实画面、自然听感、商业许可或客户最终验收。

交付源码清单由 `scripts/generate_delivery_manifest.py` 生成；提交前用 `--check` 核对实际受控文件。客户安装后按 DEPLOYMENT.md 用自己的本地素材完成机器验收。
