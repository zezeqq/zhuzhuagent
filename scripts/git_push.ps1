# Daily git commit and push
# Usage:
#   git_daily_push.bat                    -> auto message, add all, push
#   git_daily_push.bat "fix: something"   -> custom message
#   powershell -File scripts/git_push.ps1 -Auto

param(
    [string]$Message = "",
    [string]$Remote = "origin",
    [string]$Branch = "",
    [string]$UserName = "",
    [string]$UserEmail = "",
    [switch]$SkipPush,
    [switch]$All,
    [switch]$Auto
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
    if ($env:GIT_AUTHOR_NAME -and $env:GIT_AUTHOR_EMAIL) {
        $env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME
        $env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL
        return
    }
    $cfgName = (git config user.name 2>$null)
    $cfgEmail = (git config user.email 2>$null)
    if (-not $cfgName -or -not $cfgEmail) {
        Write-Host "Git user.name / user.email not configured." -ForegroundColor Yellow
        Write-Host "Fix (run once in PowerShell):" -ForegroundColor Yellow
        Write-Host '  git config --global user.name "zezeqq"' -ForegroundColor Yellow
        Write-Host '  git config --global user.email "1432450835@qq.com"' -ForegroundColor Yellow
        Write-Host "Or set GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL before running this script." -ForegroundColor Yellow
        exit 1
    }
}

function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw ("git failed: " + ($GitArgs -join " "))
    }
}

function Get-AutoCommitMessage {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    return "chore: auto push $ts"
}

if (-not (Test-Path ".git")) {
    Write-Host "Not a git repository." -ForegroundColor Red
    exit 1
}

if ($Auto -or [string]::IsNullOrWhiteSpace($Message)) {
    $Message = Get-AutoCommitMessage
    $All = $true
    Write-Host ""
    Write-Host "=== Git auto commit and push ===" -ForegroundColor Cyan
    $origin = git remote get-url origin 2>$null
    if ($origin) { Write-Host "Remote: $origin" -ForegroundColor DarkGray }
    Write-Host ("Message: {0}" -f $Message) -ForegroundColor DarkGray
    Write-Host ""
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
    Write-Host "Nothing to commit." -ForegroundColor Yellow
    if (-not $SkipPush) {
        Write-Host "==> try push anyway ..."
        Invoke-Git @("push", $Remote, $Branch)
    }
    exit 0
}

Write-Host ("==> commit " + @($staged).Count + " file(s)")
Invoke-Git @("commit", "-m", $Message)

if (-not $SkipPush) {
    Write-Host "==> push $Remote/$Branch"
    Invoke-Git @("push", $Remote, $Branch)
}

Write-Host "Done." -ForegroundColor Green
git log -1 --oneline
