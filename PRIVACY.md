# 隐私说明 / Privacy

## GitHub Pages 演示

- 在线页面不运行模型或服务端 API。
- 选择的图片或视频只用于浏览器本地预览，不会由项目代码上传。
- 在线报告是固定的虚构示例，与用户输入无关。
- GitHub Pages 和 GitHub 可能按其自身政策处理访问日志；本项目不额外嵌入分析脚本。

## 本地版

- 服务默认只绑定 `127.0.0.1`。
- 图片和视频的临时副本在任务结束后删除。
- 文章正文默认只在任务内存中处理；报告只保留必要片段、来源清单与正文哈希。
- 风险报告默认仅保存在统一 API 进程内存中，重启后不可恢复。
- 只有显式设置 `PERSIST_REPORTS=true` 时，报告才会写入 `logs/reports/`；该目录不会被 Git 跟踪。
- 模型首次启动会连接 Hugging Face 或明确列出的上游地址下载固定版本权重。用户素材不会上传至这些模型仓库。

## English summary

The Pages demo performs no model inference and uploads no selected media through project code. The local application binds to loopback by default, removes temporary media after processing, and keeps reports in memory unless persistence is explicitly enabled. Model artifacts may be downloaded from documented upstream providers during setup; user media is not sent to those providers.
