# DNA Work Agent 实施路线图

## 当前结论

你要的不是“聊天窗口 + RAG”，而是“本地桌面 Agent 平台”。

目标形态：

- 会看项目资料
- 会查行业标准
- 会规划多步骤任务
- 会生成 Word / Excel / PPT / Markdown / 代码
- 会打开和调用本机软件
- 会记录任务过程
- 会把结果交付成文件
- 会在危险动作前确认

## 下一轮优先开发

### 1. 新增任务中心

文件：

- `ui/task_center_page.py`
- `agent_runtime/task_state.py`
- `agent_runtime/executor.py`

目标：让每个 Agent 动作不再只是聊天回复，而是一个可追踪任务。

### 2. 新增产物中心

文件：

- `ui/artifact_page.py`
- `artifacts/artifact_manager.py`

目标：所有生成的文档、PPT、Excel、代码都进入产物列表。

### 3. 新增 Office 生成器

文件：

- `adapters/office_word_adapter.py`
- `adapters/office_excel_adapter.py`
- `adapters/office_ppt_adapter.py`

依赖：

- python-docx
- openpyxl
- python-pptx

目标：先不控制 Office GUI，优先直接生成 `.docx/.xlsx/.pptx`。

### 4. 新增 Planner

文件：

- `agent_runtime/planner.py`

目标：把用户一句话变成结构化步骤。

### 5. 新增 Tool Registry

文件：

- `agent_runtime/tool_registry.py`
- `agent_runtime/permissions.py`

目标：所有工具统一注册、统一权限、统一审计。

## 推荐开发顺序

1. 数据库新增 `task_steps`、`artifacts`、`tool_calls`。
2. UI 新增“任务中心”和“产物中心”。
3. 对话页发送消息时创建任务记录。
4. 实现 Word 生成工具。
5. 实现 PPT 生成工具。
6. 实现 Excel 生成工具。
7. 实现 Planner JSON。
8. 实现 Executor 顺序执行步骤。
9. 任务完成后在对话页显示产物卡片。
10. 再做 PyCharm / VS Code / 浏览器 / Office GUI 控制。

## 第一批可交付功能

- “根据当前项目资料生成项目技术方案 Word”
- “根据标准库生成现场测试记录 Word”
- “根据项目资料生成投标技术响应 PPT”
- “根据文件列表生成资料清单 Excel”
- “帮我创建一个 Python 脚本并保存到项目 exports”

## 暂不优先做

- 复杂 OCR
- 图像理解
- 真实鼠标键盘自动操作
- 全自动控制 PowerPoint GUI 排版
- 自动删除/覆盖重要文件

原因：先把文件级自动化和任务系统做好，稳定、可控、可交付；GUI 控制放后面做，避免一开始就不稳定。
