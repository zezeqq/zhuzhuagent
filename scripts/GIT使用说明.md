# Git 同步（一个 bat 搞定）

## 用法

双击 **`scripts/git_sync.bat`**

```
1  上传到新仓库 zhuzhuagent
2  上传到旧仓库 -agent
3  用 GitHub(zhuzhuagent) 覆盖本地（本地改动会丢失）
4  用 GitHub(-agent) 覆盖本地（本地改动会丢失）
5  查看当前状态
0  退出
```

- **上传**：自动切换 remote、暂存全部、提交（无改动则跳过）、拉取合并、推送。无需输入 `-ForceOverwrite`。
- **覆盖本地**：从 GitHub 拉取并 `reset --hard`，恢复前需输入 `Y` 确认。

## 仓库地址

| 选项 | 地址 |
|------|------|
| 新 (zhuzhuagent) | https://github.com/zezeqq/zhuzhuagent.git |
| 旧 (-agent) | https://github.com/zezeqq/-agent.git |

修改地址请编辑 `scripts/git_sync.ps1` 顶部 `$Repos`。

## 第一次使用前

```powershell
git config --global user.name "zezeqq"
git config --global user.email "1432450835@qq.com"
```

GitHub 推送密码处填 **Personal Access Token**。

## 不会上传的内容

见根目录 `.gitignore`：`.venv`、`data/*` 数据库与上传文件等。
