# 从 Git 历史恢复误删/改坏的文件
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts/git_restore_file.ps1 -Path "core/agent.py"
#   powershell -ExecutionPolicy Bypass -File scripts/git_restore_file.ps1 -Path "ui/main_window.py" -Commit "abc1234"

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$Commit = "HEAD"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".git")) {
    Write-Host "当前目录不是 Git 仓库。" -ForegroundColor Red
    exit 1
}

Write-Host "==> 从 $Commit 恢复: $Path"
git restore --source=$Commit -- $Path
if ($LASTEXITCODE -ne 0) {
    git checkout $Commit -- $Path
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "已恢复。当前工作区文件已替换为 $Commit 版本。" -ForegroundColor Green
git status -sb -- $Path
