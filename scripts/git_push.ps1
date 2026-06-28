# 日常 Git 提交并推送到 GitHub
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "fix: 修复本地检索"
#   powershell -ExecutionPolicy Bypass -File scripts/git_push.ps1 -Message "feat: 新功能" -UserName "zezeqq" -UserEmail "you@example.com"

param(
    [Parameter(Mandatory = $true)]
    [string]$Message,
    [string]$Remote = "origin",
    [string]$Branch = "",
    [string]$UserName = "",
    [string]$UserEmail = "",
    [switch]$SkipPush,
    [switch]$All
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-GitIdentity {
    param([string]$Name, [string]$Email)
    if ($Name -and $Email) {
        $env:GIT_AUTHOR_NAME = $Name
        $env:GIT_COMMITTER_NAME = $Name
        $env:GIT_AUTHOR_EMAIL = $Email
        $env:GIT_COMMITTER_EMAIL = $Email
        return
    }
    $cfgName = (git config user.name 2>$null)
    $cfgEmail = (git config user.email 2>$null)
    if (-not $cfgName -or -not $cfgEmail) {
        Write-Host "未配置 Git 身份。请设置 user.name / user.email，或传入 -UserName -UserEmail。" -ForegroundColor Yellow
        exit 1
    }
}

function Invoke-Git {
    param([string[]]$Args)
    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') 失败 (exit=$LASTEXITCODE)"
    }
}

if (-not (Test-Path ".git")) {
    Write-Host "当前目录不是 Git 仓库。" -ForegroundColor Red
    exit 1
}

if (-not $Branch) {
    $Branch = (git branch --show-current)
    if (-not $Branch) { $Branch = "main" }
}

Test-GitIdentity -Name $UserName -Email $UserEmail

Write-Host "==> git status"
git status -sb

if ($All) {
    Invoke-Git @("add", "-A")
} else {
    $unstaged = git diff --name-only
    $untracked = git ls-files --others --exclude-standard
    if ($unstaged) { Invoke-Git @("add", "--", $unstaged) }
    if ($untracked) { Invoke-Git @("add", "--", $untracked) }
}

$staged = git diff --cached --name-only
if (-not $staged) {
    Write-Host "没有需要提交的改动。" -ForegroundColor Yellow
    if (-not $SkipPush) {
        Write-Host "==> 尝试直接 push ..."
        Invoke-Git @("push", $Remote, $Branch)
    }
    exit 0
}

Write-Host "==> 将提交 $($staged.Count) 个文件"
Invoke-Git @("commit", "-m", $Message)

if (-not $SkipPush) {
    Write-Host "==> push $Remote/$Branch"
    Invoke-Git @("push", $Remote, $Branch)
}

Write-Host "完成。" -ForegroundColor Green
git log -1 --oneline
