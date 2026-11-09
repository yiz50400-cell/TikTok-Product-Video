# 商品视频纯剪辑交付工作区

先读 README.md、DEPLOYMENT.md 和 docs/local-editing-workflow.md。

- 客户默认入口为 Codex Desktop + ChatCut Desktop；剪辑读取 `.codex/skills/tiktok-product-video-editor/SKILL.md`，安装排错读取 setup-video-editor-environment Skill。
- 仅接收客户提供的本地素材/本地参考与商品、市场、数量、风格；不搜索或下载视频，不接入采集服务。缺料保存真实进度和具体缺口，等待本地补充。
- 默认在已授权任务范围直接制作，无逐步审批；客户明确要求对话精修才进入逐步确认。不得伪造用户审批，内部复核须如实记录。
- 无 BGM；静音或仅口播。通过 ChatCut MCP 原生剪辑导出，不用应用内 AI、submit_* 或 Computer Use。
- 原始素材不变，输出独立目录；登记素材 SHA256、项目、成片与逐条复核。使用 deliver_chatcut.py 验证实际导出并更新交付数。
- 保留 tk-ops-workspace/FFmpeg 旧工具用于调试与历史兼容；workflow CLI run 是显式调试/交互路径，不是自动 ChatCut 渲染器。旧工具审批要求不得伪造绕过。
- 使用 pyproject.toml + uv.lock，运行 `uv sync --frozen`；开发加 `--extra dev`，Kokoro 可选，edge-tts 属核心依赖。
- 修改前备份，原子写入。保护客户配置、素材和数据；不拷贝全局账号凭据，不提交真实密钥或客户数据，不擅自发布。
- 验证报告必须区分本机技术测试、ChatCut 只读连通、客户真实片验收和 Windows 真机验收。未经对应运行检查不得宣称部署成功。
