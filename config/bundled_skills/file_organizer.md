# 文件整理

扫描 Buddy 工作区 `exports` 目录，按扩展名分组统计，并给出可执行的整理建议。

## 何时启用

- 用户问「exports 里有什么」「导出了哪些文件」「按类型统计文件」
- 需要整理下载/导出目录，找重复格式或大文件

## 执行步骤

1. **先调用本 Skill 工具** `list_exports_inventory`（可选参数 `subpath` 子目录）
2. 解读返回的 Markdown 清单，按扩展名汇总数量
3. 若用户要操作其他目录，使用 **Filesystem MCP**（`mcp__filesystem__list_directory` / `read_file`），先确认路径在用户授权范围内
4. 给出整理建议（分类文件夹命名、可删除候选、需备份项），**移动/删除前必须向用户确认**

## 内置工具

| 工具 | 用途 |
|------|------|
| `list_exports_inventory` | 列出 exports 及子路径，按扩展名分组 |

## 推荐 MCP

- `filesystem` — 读写工作区外路径时需用户在 MCP 中心启用并配置允许目录

## 输出格式

```markdown
## 清单摘要
- 总文件数 / 扩展名种类

## 按类型
（引用 list_exports_inventory 结果）

## 建议
1. …
2. …
```

## 禁止

- 未经确认批量删除或移动文件
- 编造不存在的文件路径
