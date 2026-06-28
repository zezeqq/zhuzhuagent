# Git 脚本使用说明

本目录提供 Windows 下常用的 Git 操作脚本，适用于项目：

`d:\Lifesoftware\pythonandpycharmdata\DNA\PythonProject`

远程仓库（已配置 `origin`）：

`https://github.com/zezeqq/-agent.git`

默认分支：`main`

---

## 脚本一览

| 文件 | 用途 | 使用频率 |
|------|------|----------|
| `git_push.ps1` | **日常**：暂存改动 → 提交 → 推送 | 最常用 |
| `git_daily_push.bat` | 双击/命令行调用 `git_push.ps1` | 常用 |
| `git_initial_push.ps1` | **首次**上传（合并远程、推送） | 仅第一次 |
| `git_initial_upload.bat` | 双击调用首次上传脚本 | 仅第一次 |
| `git_restore_file.ps1` | 从历史版本恢复单个文件 | 误删时用 |
| `build.ps1` | 打包 exe（与 Git 无关） | 发版时用 |

---

## 第一次使用前（只需配置一次）

在 PowerShell 中执行（把邮箱换成你的）：

```powershell
git config --global user.name "zezeqq"
git config --global user.email "1432450835@qq.com"
```

配置后，日常脚本可省略 `-UserName` / `-UserEmail`。

GitHub 推送认证：HTTPS 推送时**密码处填 Personal Access Token**，不是 QQ/GitHub 登录密码。  
Token 创建：GitHub → Settings → Developer settings → Personal access tokens。

---

## 日常用法（改完代码就推）

### 方式 A：PowerShell（推荐）

在项目根目录执行：

```powershell
cd "d:\Lifesoftware\pythonandpycharmdata\DNA\PythonProject"

powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "fix: 修复本地检索"
```

带身份参数（未配置 global 时）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 `
  -Message "feat: 新增资料库导入" `
  -UserName "zezeqq" `
  -UserEmail "1432450835@qq.com"
```

### 方式 B：双击 bat（一键上传）

在资源管理器中**双击** `git_daily_push.bat` 即可：

- 自动暂存全部改动（`git add -A`）
- 自动生成提交说明（如 `chore: auto push 2026-06-28 15:30:00`）
- 提交并推送到 GitHub

若要自定义说明，从命令行带参数：

```bat
scripts\git_daily_push.bat "fix: 描述本次改动"
```

### 常用参数

| 参数 | 说明 |
|------|------|
| `-Message "..."` | **必填**，提交说明，建议用 `fix:` / `feat:` / `docs:` 前缀 |
| `-All` | 暂存全部文件（等同 `git add -A`） |
| `-SkipPush` | 只 commit，不 push |
| `-Branch main` | 指定分支（默认当前分支） |
| `-UserName` / `-UserEmail` | 临时指定提交者身份 |

示例：只提交不推送

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "wip: 调试中" -SkipPush
```

---

## 首次上传（新电脑 / 新克隆后一般不需要）

本项目**已完成首次推送**。仅在以下情况再用：

- 换了新目录重新 `git init`
- 换了新的 GitHub 空仓库

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_initial_push.ps1 `
  -UserName "zezeqq" `
  -UserEmail "1432450835@qq.com"
```

或双击 `git_initial_upload.bat`。

若与远程冲突且确定要用本地覆盖远程：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_initial_push.ps1 -ForceOverwrite
```

---

## 恢复误删 / 改坏的文件

从**最近一次提交**恢复：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_restore_file.ps1 -Path "core/agent.py"
```

从指定 commit 恢复（先 `git log --oneline` 查 hash）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_restore_file.ps1 -Path "ui/main_window.py" -Commit "60d72f2"
```

---

## 常见场景速查

### 1. 查看改了什么

```powershell
git status
git diff
git log --oneline -10
```

### 2. 改完一批功能，上传 GitHub

```powershell
powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "feat: 完成自动化调度"
```

### 3. 还没 commit，想丢弃某个文件的修改

```powershell
git restore path/to/file.py
```

### 4. 还没 commit，想丢弃**所有**未保存修改（慎用）

```powershell
git restore .
```

### 5. 只想撤销上一次 commit，代码保留

```powershell
git reset --soft HEAD~1
```

### 6. 别人更新了远程，先拉再推

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "merge: 同步远程"
```

---

## 提交说明怎么写（建议）

| 前缀 | 含义 | 示例 |
|------|------|------|
| `feat:` | 新功能 | `feat: 资料库支持 PDF 导入` |
| `fix:` | 修 bug | `fix: Plan 确认后未执行工具` |
| `docs:` | 文档 | `docs: 更新 README` |
| `refactor:` | 重构 | `refactor: 拆分 agent 模块` |
| `chore:` | 杂项/构建 | `chore: 更新 build.spec` |

---

## 不会进 Git 的文件

见项目根目录 `.gitignore`，主要包括：

- `__pycache__/`、`.venv/`、`.idea/`
- `build/`、`dist/`（打包产物）
- `data/*`（数据库、日志、上传文件，仅保留 `data/.gitkeep`）
- `.env`、本地密钥

**不要**把 API Key、数据库里的私密数据提交到 GitHub。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| `Author identity unknown` | 运行上文「第一次使用前」的 `git config` |
| push 要求登录失败 | 使用 GitHub Token 代替密码 |
| `Merge conflict` | 打开冲突文件删掉 `<<<<<<<` 标记，再 `git add` + `git commit` + `git push` |
| `git_push.ps1` 报错 | 确认在项目根目录执行，且 `-Message` 已填写 |
| 推送被拒绝 `non-fast-forward` | 先 `git pull origin main`，解决冲突后再 push |

---

## 不用脚本时的等价命令

日常脚本本质上执行：

```powershell
git add .
git commit -m "你的说明"
git push origin main
```

用 Cursor / VS Code 也可以：左侧「源代码管理」→ 写说明 → 提交 → 同步/推送。

---

## 推荐工作流

1. 改代码前：`git status` 确认干净或已知改动  
2. 改完一块：`git_push.ps1 -Message "..."`  
3. 大改前：`git checkout -b feature/xxx` 开分支（可选）  
4. 发 exe 前：先 push 代码，再运行 `scripts/build.ps1`  

有问题把终端完整报错贴出来即可排查。
