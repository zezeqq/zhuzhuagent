# Unified Git sync: upload to GitHub or restore local from GitHub.
# Called by git_sync.bat (menu) or directly:
#   powershell -File scripts/git_sync.ps1 -Action push -Target zhuzhu
#   powershell -File scripts/git_sync.ps1 -Action push -Target old -Message "fix: bug"
#   powershell -File scripts/git_sync.ps1 -Action restore -Target zhuzhu

param(
    [ValidateSet("push", "restore", "status", "menu")]
    [string]$Action = "menu",
    [ValidateSet("zhuzhu", "old", "")]
    [string]$Target = "",
    [string]$Message = "",
    [string]$Branch = "main",
    [string]$Remote = "origin",
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

$Repos = @{
    zhuzhu = "https://github.com/zezeqq/zhuzhuagent.git"
    old    = "https://github.com/zezeqq/-agent.git"
}
$DefaultUser = "zezeqq"
$DefaultEmail = "1432450835@qq.com"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Write-Title([string]$Text) {
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Invoke-Git {
    param([string[]]$GitArgs)
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw ("git failed: git " + ($GitArgs -join " "))
    }
}

function Ensure-Repo {
    Set-Location $Root
    if (-not (Test-Path ".git")) {
        Write-Host "Not a git repository: $Root" -ForegroundColor Red
        exit 1
    }
}

function Ensure-Identity {
    if ($env:GIT_AUTHOR_NAME -and $env:GIT_AUTHOR_EMAIL) {
        $env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME
        $env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL
        return
    }
    $name = git config user.name 2>$null
    $email = git config user.email 2>$null
    if (-not $name -or -not $email) {
        $env:GIT_AUTHOR_NAME = $DefaultUser
        $env:GIT_COMMITTER_NAME = $DefaultUser
        $env:GIT_AUTHOR_EMAIL = $DefaultEmail
        $env:GIT_COMMITTER_EMAIL = $DefaultEmail
    }
}

function Set-Origin([string]$Url) {
    $current = git remote get-url $Remote 2>$null
    if (-not $current) {
        Write-Host "Add remote $Remote -> $Url"
        Invoke-Git @("remote", "add", $Remote, $Url)
    } elseif ($current -ne $Url) {
        Write-Host "Switch remote: $current -> $Url" -ForegroundColor Yellow
        Invoke-Git @("remote", "set-url", $Remote, $Url)
    } else {
        Write-Host "Remote OK: $Url"
    }
}

function Get-AutoMessage {
    return "chore: sync " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
}

function Sync-Push {
    param(
        [Parameter(Mandatory = $true)][string]$TargetKey,
        [string]$CommitMessage = ""
    )
    $url = $Repos[$TargetKey]
    Write-Title "Upload to $TargetKey"
    Write-Host $url

    Ensure-Repo
    Ensure-Identity
    Set-Origin $url

    $cur = git branch --show-current
    if ($cur -ne $Branch) {
        Invoke-Git @("branch", "-M", $Branch)
    }

    Write-Host ""
    git status -sb

    Invoke-Git @("add", "-A")
    $staged = @(git diff --cached --name-only)
    if ($staged.Count -gt 0) {
        if (-not $CommitMessage) { $CommitMessage = Get-AutoMessage }
        Write-Host "Commit $($staged.Count) file(s): $CommitMessage"
        Invoke-Git @("commit", "-m", $CommitMessage)
    } else {
        Write-Host "No local changes to commit." -ForegroundColor DarkGray
    }

    Write-Host "Fetch remote ..."
    Invoke-Git @("fetch", $Remote)

    $remoteHead = git ls-remote --heads $Remote $Branch 2>$null
    $forcePush = $false

    if ($remoteHead) {
        $mergeBase = git merge-base HEAD "$Remote/$Branch" 2>$null
        $remoteCount = 0
        $localAhead = 0
        try { $remoteCount = [int](git rev-list --count "$Remote/$Branch" 2>$null) } catch {}
        try { $localAhead = [int](git rev-list --count "$Remote/$Branch..HEAD" 2>$null) } catch {}

        if (-not $mergeBase) {
            if ($remoteCount -le 2 -and $localAhead -gt 0) {
                Write-Host "Remote only has GitHub init commit; use local project to replace it."
                $forcePush = $true
            } else {
                Write-Host "Merge unrelated histories (one-time) ..."
                git pull $Remote $Branch --allow-unrelated-histories --no-edit
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "Merge failed; will push local and replace remote main." -ForegroundColor Yellow
                    git merge --abort 2>$null
                    $forcePush = $true
                }
            }
        } else {
            $behind = git rev-list --count "HEAD..$Remote/$Branch" 2>$null
            if ($behind -and [int]$behind -gt 0) {
                Write-Host "Remote is ahead, rebasing ..."
                git pull $Remote $Branch --rebase --autostash
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "Rebase failed. Try restore from GitHub (menu 3/4)." -ForegroundColor Red
                    exit 1
                }
            }
        }
    }

    Write-Host "Push ..."
    if ($forcePush) {
        Invoke-Git @("push", "-u", $Remote, $Branch, "--force")
    } else {
        Invoke-Git @("push", "-u", $Remote, $Branch)
    }

    Write-Host ""
    Write-Host "Upload done." -ForegroundColor Green
    git log -1 --oneline
}

function Sync-Restore {
    param(
        [Parameter(Mandatory = $true)][string]$TargetKey
    )
    $url = $Repos[$TargetKey]
    Write-Title "Restore local from $TargetKey (discard local changes)"
    Write-Host $url
    Write-Host "Branch: $Branch" -ForegroundColor Yellow
    Write-Host "WARNING: All uncommitted local changes will be LOST." -ForegroundColor Red

    if (-not $Yes) {
        $confirm = Read-Host "Type Y to continue"
        if ($confirm -ne "Y" -and $confirm -ne "y") {
            Write-Host "Cancelled."
            exit 0
        }
    }

    Ensure-Repo
    Set-Origin $url

    Write-Host "Fetch ..."
    Invoke-Git @("fetch", $Remote)

    $remoteHead = git ls-remote --heads $Remote $Branch 2>$null
    if (-not $remoteHead) {
        Write-Host "Remote branch $Remote/$Branch does not exist." -ForegroundColor Red
        exit 1
    }

    $cur = git branch --show-current
    if ($cur -ne $Branch) {
        Invoke-Git @("checkout", "-B", $Branch, "$Remote/$Branch")
    } else {
        Invoke-Git @("reset", "--hard", "$Remote/$Branch")
    }

    git clean -fd

    Write-Host ""
    Write-Host "Local restored from GitHub." -ForegroundColor Green
    git log -1 --oneline
    git status -sb
}

function Show-Status {
    Write-Title "Git status"
    Ensure-Repo
    git remote -v
    Write-Host ""
    git status -sb
    Write-Host ""
    git log -3 --oneline
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "=============================="
        Write-Host "  Git Sync"
        Write-Host "=============================="
        Write-Host "  1  Upload -> zhuzhuagent (new)"
        Write-Host "  2  Upload -> -agent (old)"
        Write-Host "  3  Restore local from zhuzhuagent"
        Write-Host "  4  Restore local from -agent"
        Write-Host "  5  Show status"
        Write-Host "  0  Exit"
        Write-Host "=============================="
        $c = Read-Host "Choose"
        switch ($c) {
            "1" { Sync-Push -TargetKey zhuzhu; Read-Host "Press Enter" }
            "2" { Sync-Push -TargetKey old; Read-Host "Press Enter" }
            "3" { Sync-Restore -TargetKey zhuzhu; Read-Host "Press Enter" }
            "4" { Sync-Restore -TargetKey old; Read-Host "Press Enter" }
            "5" { Show-Status; Read-Host "Press Enter" }
            "0" { return }
            default { Write-Host "Invalid choice." -ForegroundColor Yellow }
        }
    }
}

switch ($Action) {
    "push" {
        if (-not $Target) { Write-Host "Missing -Target zhuzhu|old"; exit 1 }
        Sync-Push -TargetKey $Target -CommitMessage $Message
    }
    "restore" {
        if (-not $Target) { Write-Host "Missing -Target zhuzhu|old"; exit 1 }
        Sync-Restore -TargetKey $Target
    }
    "status" { Show-Status }
    "menu"   { Show-Menu }
}
