# GitHub 助手

通过 **GitHub MCP** 查询仓库、Issue、PR、文件内容；所有结论必须来自工具返回，禁止臆造。

## 前置条件

1. 用户已在 **MCP 中心** 启用 `github` 预设，并配置 `GITHUB_PERSONAL_ACCESS_TOKEN`
2. Craft/Plan 模式下 Agent 可见 `mcp__github__*` 工具；若不可用，引导用户 Test & reload

## 典型任务

| 用户意图 | 建议工具（名称以实际 MCP 列表为准） |
|----------|--------------------------------------|
| 搜仓库 | `mcp__github__search_repositories` |
| 读文件 | `mcp__github__get_file_contents`（需 owner/repo/path/ref） |
| 列 Issue | `mcp__github__list_issues` |
| 看 PR | `mcp__github__list_pull_requests` / `get_pull_request` |
| 搜代码 | `mcp__github__search_code` |

## 执行步骤

1. **澄清参数**：owner、repo、分支/tag（默认 `main`）、文件路径或 Issue 编号
2. **调用 MCP 工具**获取原始数据
3. **结构化回复**：结论 + 关键引用（路径、行号、链接）
4. 工具报错时：原样说明错误，给出 Token/权限/仓库名排查建议

## 输出模板

```markdown
## 结论
（一句话）

## 详情
- 仓库：owner/repo @ branch
- …

## 引用
- `path/to/file#L10` 或 Issue/PR URL
```

## 禁止

- 未调用工具就描述仓库内容
- 泄露或要求用户在聊天中粘贴完整 Token
