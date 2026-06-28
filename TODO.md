# TODO

## WorkBuddy 风格三栏工作台 — 已完成

- 已完成：重构主窗口为三栏布局（QSplitter）：任务侧边栏 | 对话面板 | 结果面板。
- 已完成：删除 19 个独立页面，合并为统一工作台体验。
- 已完成：实现 Ask/Craft/Plan 三种工作模式选择器。
- 已完成：创建 QThread worker 类（AgentWorker/ExecutorWorker/PlanWorker），异步执行不阻塞 UI。
- 已完成：实现 DB 驱动的任务列表侧边栏，支持搜索、状态筛选、右键删除。
- 已完成：实现统一对话面板，支持消息流、步骤进度卡片、产物卡片、执行计划卡片。
- 已完成：实现结果面板（产物/文件/预览/变更四个 tab）。
- 已完成：合并设置/模型/项目/文件库/标准库/连接器/记忆/日志为统一设置对话框。
- 已完成：升级 QSS 主题，支持 @TOKEN 变量替换，全面适配三栏布局。
- 已完成：Executor 支持 step_callback、cancel_check 和 conversation_id 关联。
- 已完成：ModelClient 新增 stream_chat() 流式输出。
- 已完成：新增 conversation_manager.py，会话和消息持久化到 SQLite。
- 已完成：数据库迁移：conversations 表增加 mode/status 列，tasks 表增加 conversation_id 列。
- 已完成：清理废弃代码：icons.py、空壳 manager、重复的 TASK_KEYWORDS、重复的 safety_manager。

## 后续优化

- 增加流式输出在对话面板中的逐字显示。
- 增加向量数据库：Chroma、FAISS 或本地 embedding。
- 增加 LLM 辅助的智能 Planner（当前为规则兜底）。
- 增加工作流自动执行引擎。
- 增加 GUI 自动化：截图、OCR、鼠标键盘控制。
- 增加浏览器自动化：网页读取、搜索、表单填写。
- 增加 Skill 包签名/风险扫描、依赖安装、版本更新和卸载。
- 增加 Office 文档更专业的样式和主题。
- 增加 Diff 预览和版本管理。
- 增加 PyInstaller 打包配置和图标资源。
- 增加快捷键支持（Ctrl+K 新建任务等）。
