# SQL 数据分析

将业务问题转化为 **只读 SQL**，并解释查询逻辑与结果解读方式。

## 何时启用

- 写查询、解释 SQL、设计统计口径、看表结构怎么 JOIN

## 执行步骤

1. **确认 schema**（缺则追问）：
   - 表名、关键字段、主外键、样本数据行数级
   - 数据库类型（MySQL / PostgreSQL / SQLite / SQL Server）
2. 用自然语言复述分析目标，与用户确认
3. 编写 **SELECT** 语句（必要时用 CTE 分步）
4. 解释：每段 SQL 做什么、结果列含义、注意事项（索引、LIMIT）
5. 若用户提供 CSV：可用 `file_read` 看前几行推断字段，但 SQL 仍针对用户声明的表

## 约束（必须遵守）

- **禁止** `DELETE` / `UPDATE` / `INSERT` / `DROP` / `TRUNCATE`
- 大表默认加 `LIMIT`（如 1000）并说明
- 不确定字段名时先问，不用 `SELECT *` 糊弄

## 输出模板

```markdown
## 分析目标
…

## 假设
- 表 `orders` 含 …

## SQL

（在此给出 ```sql 代码块）

## 说明
- …

## 若结果异常
- 检查 …

## 推荐工具

- `file_read` — 查看用户提供的 schema 文档或 CSV 样例
