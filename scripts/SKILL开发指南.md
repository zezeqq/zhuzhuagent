# Skill 包开发指南

Buddy 的 Skill 与 Cursor Agent Skill 类似：**SKILL.md 注入 prompt**，可选 **skill.py 注册工具**。

## 目录结构

```
installed_skills/my_skill/
  SKILL.md       # 必需 — Agent 行为说明
  skill.json     # manifest（元数据）
  skill.py       # 可选 — Tool Skill 的 Python 入口
```

## skill_type

| 类型 | 说明 |
|------|------|
| `prompt` | 仅 SKILL.md，引导 Agent 使用内置/MCP 工具 |
| `tool` | manifest 含 `tools[]` + skill.py 实现 |
| `planned` | 商店展示用，不可安装 |

## manifest 示例（prompt）

```json
{
  "name": "ppt_maker",
  "display_name": "PPT 制作",
  "skill_type": "prompt",
  "prompt_entry": "SKILL.md",
  "entry": "skill.py",
  "recommended_tools": ["office_ppt_create"],
  "recommended_mcp": []
}
```

## manifest 示例（tool）

```json
{
  "name": "file_organizer",
  "skill_type": "tool",
  "entry": "skill.py",
  "tools": [{
    "name": "list_exports_inventory",
    "description": "列出 exports 目录文件",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }]
}
```

## skill.py 约定

```python
def list_exports_inventory(args: dict) -> str:
    ...

def handle(args: dict) -> str:
    tool = args.get("_tool") or ""
    ...
```

也兼容旧版 `run(**kwargs)`，但推荐 `handle(args) -> str`。

## 与 MCP 配合

在 manifest 或 SKILL.md 中声明：

```json
"recommended_mcp": ["fetch", "puppeteer"]
```

Agent 会在 Skill 段落末尾提示对应 `mcp__*` 工具名。

## 安装方式

1. **技能商店** — 从 `core/skill_catalog.py` 安装  
2. **URL / GitHub** — 技能商店「从 URL 安装」  
3. **上传 ZIP** — 我的 Skill → 上传技能包  

## 对话中使用

- 底栏 **Skill: 全部 / 指定 Skill** — 只注入选中 Skill 的 prompt  
- **Craft / Plan** 模式生效  
- 我的 Skill → **预览注入** 查看将发送给模型的文本  

## 添加到商店 catalog

编辑 `core/skill_catalog.py` 的 `RECOMMENDED_SKILLS`，设置 `skill_type`、`skill_md`、`tools` 等，专家中心与技能商店自动同步。

## 遗留说明

- 数据库 `skills` 表 + `skills/*.py` 为早期内置函数注册，与 SKILL.md 包体系独立；新 Skill 请用 `installed_skill_packages`。
