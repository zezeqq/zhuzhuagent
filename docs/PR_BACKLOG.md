# 🐷🐷Buddy 改造 PR 清单

> 基于 2026-06 代码审计。每个 PR 尽量 **单一职责、可独立合并、可验收**。  
> 依赖关系见文末 DAG。

---

## Phase 0 — 修「名不副实」（优先，约 1–2 周）

### PR-01：Ask 模式真正「只问答、不调工具」

**问题**：三种模式都走 `Agent.run()` + 全工具链，「问一问」名不副实。

**改动文件**

| 文件 | 改动 |
|------|------|
| `core/agent.py` | `run()` 开头：`mode=="ask"` 时走 `answer()` 或等价无工具路径，yield `final_reply` 后 return |
| `agent_runtime/tool_definitions.py` | 可选：`get_active_tools(mode=...)` 供 ask 返回 `[]` |
| `ui/workers.py` | `AgentWorker.run` 传 mode；ask 时不挂 `request_permission` |
| `ui/conversation_panel.py` | ask 模式隐藏/禁用「完全访问」提示文案（可选） |
| `core/agent.py` `SYSTEM_PROMPT` | ask 专用短 prompt：禁止 tool_calls |

**验收**

- [ ] Ask 模式下用户问「打开酷狗」，Agent **只文字回答**，不出现 tool_call 卡片
- [ ] Craft/Plan 行为不变
- [ ] 会话 `conversations.mode` 仍为 `ask`

**估时**：0.5–1 天

---

### PR-02：「本地检索」真正不调用 LLM

**问题**：模型下拉选「本地检索」时 `currentData()` 为 `None`，但 `Agent.run` 会 `model or default_model()` 回退。

**改动文件**

| 文件 | 改动 |
|------|------|
| `ui/conversation_panel.py` | `_run_agent`：若 `model is None` 且非误触，走 `_run_local_search(text)` |
| `core/agent.py` | 新增 `local_search(user_text, project)` 或在 `answer()` 中 `model=None` 分支调用 `_local_answer` + RAG |
| `ui/workers.py` | 可选：`LocalSearchWorker`（轻量 QThread）避免阻塞 UI |
| `rag/retriever.py` | 确保无 chunks 时返回友好文案 |

**验收**

- [ ] 选「本地检索」+ 未配置模型 → 仍能返回知识库命中结果
- [ ] 网络/API 不可用时本地检索可用
- [ ] 选具体模型时仍走 Agent.run

**估时**：0.5 天  
**依赖**：无（可与 PR-01 并行）

---

### PR-03：Plan 模式 — 计划卡片 + 确认后再执行

**问题**：Plan 仅追加 `PLAN_MODE_SUFFIX`；`PlanMessage` UI 从未展示；工具从第一轮就可调用。

**改动文件**

| 文件 | 改动 |
|------|------|
| `core/agent.py` | plan 第一轮：`tools=[]` 或仅 `file_read`/`file_list`；system 要求输出 JSON/Markdown 计划 |
| `ui/conversation_panel.py` | 解析 plan 回复 → 实例化 `PlanMessage`；用户点「执行计划」再 `_run_agent(..., mode="craft", plan_context=...)` |
| `ui/widgets/message_widget.py` | `PlanMessage` 增加「执行 / 修改 / 取消」Signal（若尚未有） |
| `agent_runtime/planner.py` | 可选：复用规则 planner 作 plan 模式兜底 |

**验收**

- [ ] Plan 模式首轮只出计划，**无** software_launch 等工具调用
- [ ] 点击「执行计划」后进入 Craft 工具链
- [ ] 点「取消」不触发 Agent

**估时**：1–2 天  
**依赖**：建议 PR-01 合并后做（模式语义清晰）

---

### PR-04：连接器 / MCP UI 诚实化（二选一，本 PR 先做 A）

**方案 A（推荐，快）**：改文案 + 删 MCP 假配置  
**方案 B（慢）**：接入 MCP Client

#### PR-04A：文案与入口修正

| 文件 | 改动 |
|------|------|
| `ui/pages/expert_center_page.py` | 「连接器」改为「快捷启动」；状态灯改「运行中/未检测到进程」 |
| `ui/dialogs/connector_dialog.py` | 删除或隐藏 MCP JSON 编辑；或文件头标注 `@deprecated` |
| `ui/dialogs/settings_dialog.py` | 若有 MCP 入口则移除 |
| `ui/i18n.py` | 更新中英文描述 |

**验收**

- [ ] 用户不会误以为已接入飞书/腾讯文档 API
- [ ] exe 路径配置 + 启动仍可用

**估时**：0.5 天

#### PR-04B：MCP 运行时（独立 PR，Phase 1）

| 文件 | 改动 |
|------|------|
| 新建 `agent_runtime/mcp_client.py` | 读 `mcp_config`，stdio/SSE 启动 server，枚举 tools |
| `agent_runtime/tool_definitions.py` | 合并 MCP tools 到 `get_active_tools()` |
| `core/settings_runtime.py` | MCP 工具权限分类 |
| `ui/dialogs/connector_dialog.py` | 重新启用并接到设置页 |

**估时**：3–5 天

---

### PR-05：流式输出接入对话面板

**问题**：`ModelClient.stream_chat()` 已实现，UI 未用。

**改动文件**

| 文件 | 改动 |
|------|------|
| `core/model_client.py` | 确认 `stream_chat` 与 `chat_with_tools` 非流式 final 兼容 |
| `core/agent.py` | 最后一轮无 tool_calls 时可选 stream yield `token` 事件 |
| `ui/workers.py` | 新 Signal `token = Signal(str)` |
| `ui/conversation_panel.py` | `_handle_token` 追加到 `AgentMessage` |
| `ui/widgets/message_widget.py` | `AgentMessage.append_token(text)` |
| `core/settings_store.py` | 可选开关 `enable_streaming`（默认开） |

**验收**

- [ ] 纯文本回复逐字/逐块显示
- [ ] 工具调用轮次仍用现有卡片 UI
- [ ] 停止按钮可中断 stream

**估时**：1–2 天  
**依赖**：无

---

## Phase 1 — 体验与可观测性（约 2–3 周）

### PR-06：Executor 接入主聊天路径

**问题**：`agent_runtime/executor.py` 完整但未调用；「变更」Tab 常空。

| 文件 | 改动 |
|------|------|
| `ui/conversation_panel.py` | `_run_agent` 开始时 `create_task`（或 Executor.create） |
| `ui/workers.py` | tool_call 时写 `task_steps` |
| `core/conversation_manager.py` | 可选：`link_task_conversation` |
| `ui/result_panel.py` | `_refresh_changes` 按 `conversation_id` 查 steps |

**验收**

- [ ] 一次多工具对话后，「变更」Tab 有步骤输入/输出
- [ ] `task_created.emit` 真正触发（`main_window` 接结果面板）

**估时**：1–2 天

---

### PR-07：自动化调度（Windows 任务计划）

**问题**：「每日/每周提醒」模板名不副实，仅立即 `replay_agent`。

| 文件 | 改动 |
|------|------|
| 新建 `core/automation_scheduler.py` | 持久化规则 JSON；注册 schtasks / APScheduler |
| `ui/pages/automation_page.py` | 创建规则 UI：cron/每日时间/启用开关 |
| `main.py` | 启动时 `scheduler.start()` |
| `db/schema.sql` + migration | 表 `automation_rules` |

**验收**

- [ ] 「父母联系提醒」可设每周日 10:00 触发
- [ ] 触发时新建会话并 `replay_agent`
- [ ] 可禁用/删除规则

**估时**：2–3 天

---

### PR-08：向量 RAG + 资料库入口

| 文件 | 改动 |
|------|------|
| 新建 `rag/embedder.py`、`rag/vector_store.py` | Chroma 或 sqlite-vec |
| `rag/retriever.py` | 混合检索：向量 + LIKE 兜底 |
| `ui/pages/more_page.py` | 「知识库」→ 文件导入 + 索引状态 |
| `core/file_manager.py` | 接 UI：导入 → `index_file` |
| `requirements.txt` | 增加 embedding 依赖（可选本地模型） |

**验收**

- [ ] 导入 PDF/MD 后可语义检索
- [ ] Agent 回答带 citation

**估时**：3–5 天

---

### PR-09：项目上下文增强

| 文件 | 改动 |
|------|------|
| `core/agent.py` `_build_system_prompt` | 注入 `project_description`、关联文件列表 |
| `ui/pages/project_page.py` | 「指令」保存到 DB 已有字段，确认读写一致 |
| 可选 | 项目级 `.buddy/rules.md` 读取 |

**验收**

- [ ] 项目页写的背景出现在 system prompt
- [ ] 切换项目后 Agent 行为随项目变

**估时**：0.5–1 天

---

### PR-10：GUI 任务验证与重试

| 文件 | 改动 |
|------|------|
| `core/agent.py` | tool 失败后允许 1 次 `ui_locate` 验证步骤 |
| `agent_runtime/tool_executor.py` | 统一返回「是否成功」结构 |
| `core/agent.py` SYSTEM_PROMPT | 强化「执行后 ui_locate 确认」 |

**验收**

- [ ] 「打开酷狗搜夜曲」类任务有 locate 验证日志

**估时**：1–2 天

---

## Phase 2 — 清理与 polish（可穿插）

### PR-11：删除 / 隐藏 dead code

| 项 | 文件 |
|----|------|
| 未引用对话框 | `ui/dialogs/connector_dialog.py`、`expert_dialog.py` 合并或删除 |
| 无效设置项 | `enable_animations`、`auto_install_low_risk` 实现或从 settings 移除 |
| 未 emit 信号 | `task_created`、`artifact_created` 实现或移除 connect |
| Skill 双 catalog | 统一 `core/skill_catalog.py` 为唯一来源 |

**估时**：1 天

---

### PR-12：任务侧栏与菜单小功能

| 项 | 文件 |
|----|------|
| 置顶 / 重命名 | `task_sidebar.py` + `conversations.pinned`/`title` |
| 通知中心占位 | 或移除 🔔 按钮 |
| 帮助 → 独立日志查看 | `app_menu.py` + `utils/path_utils.log_file` |

**估时**：1–2 天

---

### PR-13：国际化补全

| 文件 |
|------|
| `ui/pages/project_page.py`、`expert_center_page.py`、`automation_page.py`、`more_page.py` |
| `ui/i18n.py` 补 key + `retranslate_*` |

**估时**：1–2 天

---

## 推荐合并顺序（DAG）

```
PR-01 (Ask) ──────┐
PR-02 (本地检索) ─┼──► PR-03 (Plan) ──► PR-06 (Executor)
PR-04A (连接器文案)│
PR-05 (流式) ─────┘

PR-06 ──► PR-07 (调度)
PR-08 (向量RAG) 与 PR-09 (项目上下文) 可并行
PR-11 (清理) 任意时刻
PR-04B (MCP) 独立长线
```

## 第一周建议 Sprint（最小可交付）

| 天 | PR | 交付物 |
|----|-----|--------|
| D1 | PR-01 + PR-02 | 三模式语义正确 + 本地检索可用 |
| D2 | PR-04A + PR-11 部分 | 不再有 MCP 误导 |
| D3–D4 | PR-05 | 流式对话 |
| D5 | PR-03 起步 | Plan 卡片 MVP |

---

## 每个 PR 通用 Checklist

- [ ] `python main.py` 手动冒烟
- [ ] 不破坏 `allow_app_launch` / 安全中心权限
- [ ] 新 UI 文案进 `ui/i18n.py`（若用户可见）
- [ ] 不提交 API Key / 本地 database.sqlite
- [ ] 更新 `TODO.md` 对应条目

---

## 参考：主流 Agent 能力对照

| 能力 | Manus / Claude CU | 当前 Buddy | 对应 PR |
|------|-------------------|------------|---------|
| 纯聊天 vs 执行分离 | ✅ | ❌ | PR-01, PR-03 |
| 流式回复 | ✅ | ❌ | PR-05 |
| 多步任务可观测 | ✅ | 部分 | PR-06 |
| 定时自动化 | ✅ | ❌ | PR-07 |
| 语义检索 | ✅ | LIKE | PR-08 |
| MCP / 插件 | ✅ | 假 | PR-04B |
| 文件夹级权限 | Dispatch | 工具级 | 已有安全中心 |
| Computer Use | ✅ | 部分(ui_*) | PR-10 |

---

*文档版本：2026-06-28 · 随实现进度勾选 PR 验收项*
