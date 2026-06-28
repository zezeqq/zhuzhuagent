# MCP 配置向导

帮助用户在 Buddy 中启用、测试 MCP Server，并给出可复制的配置片段。

## 何时启用

- 「MCP 连不上」「没有 mcp__ 工具」「GitHub/Filesystem 怎么用」
- Test & reload 失败、npx 报错

## Buddy 内路径

1. **专家 → MCP** 或 **设置 → 工具 → MCP**
2. 从预设添加：`filesystem`、`fetch`、`github` 等
3. 填写 env（如 GitHub Token），点 **Test & reload**
4. 在 **Craft/Plan** 对话中确认工具列表出现 `mcp__<server_id>__*`

## 排查清单

| 现象 | 处理 |
|------|------|
| `npx` 不是内部或外部命令 | 安装 Node.js LTS，重启 Buddy，确认 PATH |
| GitHub 401/403 | 检查 PAT 权限（repo/read 等），env 名 `GITHUB_PERSONAL_ACCESS_TOKEN` |
| Filesystem 拒绝路径 | 在 MCP 配置的 `args` 中加入允许访问的目录绝对路径 |
| 工具列表为空 | 查看 Test 输出 stderr；防火墙/代理是否拦截 npm |

## 执行步骤

1. 问清用户要用的 MCP 名称与目标（读本地文件 / 抓网页 / GitHub）
2. 对照 `config/mcp_presets.json` 中的 command/args/env 给出配置示例
3. 指导 Test & reload 并让用户贴错误日志（可打码 Token）
4. 成功后说明对应工具前缀，如 `mcp__fetch__` / `mcp__github__`

## 输出

- 分步骤操作说明（编号列表）
- 一段可复制的 JSON 配置（env 用占位符 `YOUR_TOKEN`）

## 禁止

- 让用户在对话里发送真实 Token 明文（应写在 MCP 配置 env 中）
