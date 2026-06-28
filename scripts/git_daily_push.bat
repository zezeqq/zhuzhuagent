@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if "%~1"=="" (
  echo 用法: git_daily_push.bat "提交说明"
  echo 示例: git_daily_push.bat "fix: 修复 Plan 确认流"
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_push.ps1" -Message "%*"
pause
