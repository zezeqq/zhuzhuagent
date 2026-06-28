# Buddy - Windows release build
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Python = "python"
if (Test-Path ".venv\Scripts\python.exe") {
    $Python = ".venv\Scripts\python.exe"
    Write-Host "==> Using venv: $Python"
}

Write-Host "==> Install / verify dependencies (requirements.txt) ..."
& $Python -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "==> Verify MCP SDK ..."
& $Python -c "import mcp; from mcp.client.stdio import stdio_client"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: mcp package missing. Run: pip install mcp" -ForegroundColor Red
    exit 1
}

Write-Host "==> Check PyInstaller ..."
& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install pyinstaller
}

Write-Host "==> Clean old build ..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

Write-Host "==> PyInstaller onedir build ..."
& $Python -m PyInstaller build.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$AppName = & $Python -c "from core.app_identity import APP_NAME; print(APP_NAME)"
$OutDir = Join-Path $Root "dist\$AppName"
Write-Host ""
Write-Host "Done: $OutDir"
Write-Host ""
Write-Host "Ship the WHOLE folder dist\$AppName to other PCs (not exe alone)."
Write-Host "See scripts/打包说明.md for MCP / Node.js / API key checklist."
Write-Host "First run creates data\database.sqlite next to the exe."
Write-Host "Configure API keys in Settings. Do NOT copy dev database.sqlite."

$DataDir = Join-Path $OutDir "data"
@("exports", "installed_skills", "logs", "uploads", "standards", "skill_downloads") | ForEach-Object {
    $p = Join-Path $DataDir $_
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

Write-Host "==> Created empty data subfolders in release dir"

$PackDoc = Join-Path $Root "scripts\打包说明.md"
if (Test-Path $PackDoc) {
    Copy-Item $PackDoc (Join-Path $OutDir "使用说明-MCP与分发.md") -Force
    Write-Host "==> Copied 使用说明-MCP与分发.md into release folder"
}
