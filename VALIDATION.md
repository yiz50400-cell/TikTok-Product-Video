# 公开交付版验证记录

验证日期：2026-10-16。

- 基于员工已验证的 v0.2.0 源码交付包整理。
- 保留的 26 个 Python、PowerShell 和 PNG 文件与原交付包逐文件 SHA-256 一致。
- 项目依赖按现有 uv.lock 安装，Python 3.12.14。
- pytest -q：9 passed。
- video-compliance CLI、素材探测、素材准备和下载辅助脚本的 --help 检查通过。
- 工作区 doctor 确认项目结构有效，视频能力配置存在。
- 核对交付文件中的常见密钥、访问令牌、私钥和凭据 URL 模式，未发现命中；本检查不构成完整安全审计。
- 本次在 macOS 上验证 Python 测试、入口和交付文件；没有在本机执行 Windows PowerShell 渲染。客户电脑仍需按 DEPLOYMENT.md 配置环境并运行剪辑验收。
- 员工电脑原始运行记录见 SOURCE-VALIDATION.md。
