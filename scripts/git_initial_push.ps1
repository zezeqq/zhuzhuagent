# First push to GitHub (merge remote initial commit if needed)
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/git_initial_push.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/git_initial_push.ps1 -UserName "zezeqq" -UserEmail "you@example.com"
#   powershell -ExecutionPolicy Bypass -File scripts/git_initial_push.ps1 -ForceOverwrite

param(
    [string]$Remote = "origin",
    [string]$Branch = "main",
    [string]$UserName = "",
    [string]$UserEmail = "",
    [string]$CommitMessage = "initial commit: Buddy desktop agent baseline",
    [switch]$ForceOverwrite
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
        Write-Host ""
        Write-Host "Git identity not configured." -ForegroundColor Yellow
        Write-Host "Run: git config --global user.name YOUR_NAME"
        Write-Host "Run: git config --global user.email YOUR_EMAIL"
        Write-Host "Or pass: -UserName zezeqq -UserEmail you@example.com"
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

Write-Host "==> Project: $Root"

if (-not (Test-Path ".git")) {
    Write-Host "Not a git repository." -ForegroundColor Red
    exit 1
}

$remoteUrl = git remote get-url $Remote 2>$null
if (-not $remoteUrl) {
    Write-Host "Remote '$Remote' not found." -ForegroundColor Yellow
    Write-Host "Example: git remote add origin https://github.com/zezeqq/-agent.git"
    exit 1
}
Write-Host "==> Remote: $Remote -> $remoteUrl"

Test-GitIdentity -Name $UserName -Email $UserEmail

Write-Host "==> Check commits ..."
$hasCommit = $true
try {
    Invoke-Git @("rev-parse", "HEAD") | Out-Null
} catch {
    $hasCommit = $false
}

if (-not $hasCommit) {
    Invoke-Git @("add", "-A")
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host "Nothing to commit." -ForegroundColor Yellow
        exit 1
    }
    Invoke-Git @("commit", "-m", $CommitMessage)
    Write-Host "Created initial local commit." -ForegroundColor Green
}

$currentBranch = (git branch --show-current)
if ($currentBranch -ne $Branch) {
    Write-Host "==> Rename branch: $currentBranch -> $Branch"
    Invoke-Git @("branch", "-M", $Branch)
}

Write-Host "==> Fetch $Remote/$Branch ..."
Invoke-Git @("fetch", $Remote)

$remoteExists = git ls-remote --heads $Remote $Branch 2>$null
if ($remoteExists) {
    if ($ForceOverwrite) {
        Write-Host "==> Force push ..." -ForegroundColor Yellow
        Invoke-Git @("push", "-u", $Remote, $Branch, "--force")
    } else {
        $mergeBase = git merge-base HEAD "$Remote/$Branch" 2>$null
        if (-not $mergeBase) {
            Write-Host "==> Merge unrelated histories ..."
            git pull $Remote $Branch --allow-unrelated-histories --no-edit
            if ($LASTEXITCODE -ne 0) {
                Write-Host ""
                Write-Host "Merge conflict. Resolve then run:" -ForegroundColor Yellow
                Write-Host "  git add ."
                Write-Host "  git commit -m merge-remote"
                Write-Host "  git push -u $Remote $Branch"
                Write-Host ""
                Write-Host "Or rerun with -ForceOverwrite to replace remote." -ForegroundColor Yellow
                exit 1
            }
        }
        Write-Host "==> Push to $Remote/$Branch ..."
        Invoke-Git @("push", "-u", $Remote, $Branch)
    }
} else {
    Write-Host "==> First push to new remote branch ..."
    Invoke-Git @("push", "-u", $Remote, $Branch)
}

Write-Host ""
Write-Host "Done: $remoteUrl" -ForegroundColor Green
Write-Host "Daily: scripts/git_push.ps1 -Message your_change_summary"
