# DNA Work Agent

DNA Work Agent 是一个面向工程技术领域的本地 AI 桌面 Agent 平台，采用 WorkBuddy 风格的三栏工作台设计。

## 界面布局

```
┌──────────────────────────────────────────────────────────────────┐
│  DNA Work Agent    编辑(E)    窗口(W)    帮助(H)     ◧ 结果面板  │
├────────────┬──────────────────────────────┬──────────────────────┤
│ 左栏        │ 中栏 — 对话区               │ 右栏 — 结果区        │
│            │                              │                      │
│ ＋ 新建任务 │ [问一问] [做一做] [想一想]    │ 产物 | 文件 | 预览   │
│ 搜索任务…  │  模型: DeepSeek / deepseek   │                      │
│            │                              │ 📄 技术方案.docx     │
│ 全部 进行中 │  DNA Agent                   │ 📊 资料清单.xlsx     │
│            │  > 已生成投标技术方案…         │ 📑 汇报PPT.pptx     │
│ ⚡ 生成PPT │                              │                      │
│ ⚡ 资料清单 │  ● 1. 生成 PPTX ✓            │                      │
│ 💬 标准查询 │                              │                      │
│            │ ┌────────────────────────┐   │                      │
│            │ │ 输入任务或问题…        │   │                      │
│ D DNA 用户 │ │                   发送 │   │                      │
│         ⚙ │ └────────────────────────┘   │                      │
└────────────┴──────────────────────────────┴──────────────────────┘
```

## 核心功能

- **三种工作模式**：问一问（Ask）仅问答 / 做一做（Craft）直接执行 / 想一想（Plan）先规划后执行
- **任务管理**：每个对话即一个独立任务，支持并行处理，持久化到 SQLite
- **Office 文档生成**：自动生成 Word、Excel、PPT 文件
- **知识库 RAG**：导入项目文件和行业标准 PDF，建立索引，Agent 回答时引用来源
- **异步执行**：所有 Agent/Executor 操作在后台线程运行，UI 不阻塞
- **实时进度**：任务执行过程中实时显示步骤进度和状态
- **本地软件连接**：自动检测并启动 VS Code、PyCharm、Chrome 等本机软件
- **技能安装**：从 GitHub/URL 下载并安装 Skill 包

## 运行

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 使用流程

1. 启动后进入三栏工作台，中栏显示快捷场景入口
2. 在底部输入框输入任务（如"生成投标技术响应 PPT"）
3. 选择工作模式：问一问 / 做一做 / 想一想
4. Agent 在后台执行任务，实时显示步骤进度
5. 生成的文件出现在右栏产物列表，可直接打开
6. 左栏任务列表保存所有历史任务，可随时切换

## 设置

点击左栏底部的 ⚙ 按钮打开设置对话框，包含：

- 通用设置（语言/字体/工作目录）
- 模型管理（添加/编辑/删除 LLM 配置）
- 项目管理（项目 CRUD、设为当前项目）
- 文件库（导入文件、建立索引）
- 标准库（导入标准 PDF、建立索引）
- 快捷启动（配置本机程序路径）
- 记忆管理
- 关于/日志

## Git 上传

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "fix: your change" -UserName "zezeqq" -UserEmail "1432450835@qq.com"
```

## 安全说明

- 不要把真实 API Key 写入代码仓库
- 高风险工具执行前需要确认
- 第一阶段默认只读取和索引资料，不主动修改原始文件

## 技术栈

- Python 3 + PySide6 桌面 UI
- SQLite 本地数据库
- OpenAI Compatible API（支持 20+ 国内外模型供应商）
- python-docx / openpyxl / python-pptx 文件生成
- PyMuPDF / pypdf 文档解析
