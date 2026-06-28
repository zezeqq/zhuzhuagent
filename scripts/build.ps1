# DNA Work Agent - Windows build script
# Usage: powershell -ExecutionPolicy Bypass -File scripts/build.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Check PyInstaller ..."
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    pip install pyinstaller
}

Write-Host "==> Clean old build ..."
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

Write-Host "==> PyInstaller onedir build ..."
python -m PyInstaller build.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$AppName = python -c "from core.app_identity import APP_NAME; print(APP_NAME)"
$OutDir = Join-Path $Root "dist\$AppName"
Write-Host ""
Write-Host "Done: $OutDir"
Write-Host ""
Write-Host "Ship the whole folder dist\$AppName to other PCs."
Write-Host "First run creates data\database.sqlite next to the exe."
Write-Host "Configure API keys in Settings. Do NOT copy dev database.sqlite."

$DataDir = Join-Path $OutDir "data"
@("exports", "installed_skills", "logs", "uploads", "standards", "skill_downloads") | ForEach-Object {
    $p = Join-Path $DataDir $_
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

Write-Host "==> Created empty data subfolders in release dir"
