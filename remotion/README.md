# Remotion 商品视频包装

请在项目根目录按照 [协同剪辑指南](../docs/chatcut-remotion-workflow.md) 操作。先用 package_remotion.py 准备真实本地底片，再渲染。此目录不含客户素材。

`npm run lint` 检查 TypeScript 和模板；`npm run studio -- --public-dir=/absolute/prepared/media --props=/absolute/prepared/props.json` 预览已准备的输入。默认空参数没有底片，不能作为成片。
