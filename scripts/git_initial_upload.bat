@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo 首次上传到 GitHub（origin 已指向远程仓库）
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_initial_push.ps1" %*
echo.
pause
