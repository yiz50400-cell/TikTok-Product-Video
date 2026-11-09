# 商品视频纯剪辑交付工作区

先读 README.md、DEPLOYMENT.md、docs/local-editing-workflow.md 和 docs/chatcut-remotion-workflow.md。

- 客户默认入口为 Codex Desktop + ChatCut Desktop + Remotion；剪辑读取 `.codex/skills/tiktok-product-video-editor/SKILL.md`，安装排错读取 setup-video-editor-environment Skill。
- 仅接收客户提供的本地素材/本地参考与商品、市场、数量、风格；不搜索或下载视频，不接入采集服务。缺料保存真实进度和具体缺口，等待本地补充。
- 默认在已授权任务范围直接制作，无逐步审批；客户明确要求对话精修才进入逐步确认。不得伪造用户审批，内部复核须如实记录。
- 无 BGM；静音或仅口播。ChatCut MCP 完成镜头剪辑并导出未烧字幕底片；Remotion 完成字幕、卖点卡、标题和CTA包装。不用应用内 AI、submit_* 或 Computer Use。
- 原始素材不变，输出独立目录；登记素材 SHA256、项目、成片与逐条复核。用 package_remotion.py 准备/包装，再用 deliver_video.py 验证最终成片及真实复核记录并更新交付数；deliver_chatcut.py 保持兼容。
- 保留 tk-ops-workspace/FFmpeg 旧工具用于调试与历史兼容；workflow CLI run 是显式调试/交互路径，不是自动 ChatCut 渲染器。旧工具审批要求不得伪造绕过。
- 使用 pyproject.toml + uv.lock，运行 `uv sync --frozen`；开发加 `--extra dev`，Kokoro 可选，edge-tts 属核心依赖。
- 修改前备份，原子写入。保护客户配置、素材和数据；不拷贝全局账号凭据，不提交真实密钥或客户数据，不擅自发布。
- 验证报告必须区分本机技术测试、ChatCut 只读连通、客户真实片验收和 Windows 真机验收。未经对应运行检查不得宣称部署成功。

- Remotion 的渲染完成仅是 RENDERED_PENDING_REVIEW；不自动代写观看/试听证据。保留 ChatCut 项目 ID、底片与原素材哈希，不宣称可逆多轨工程同步。
