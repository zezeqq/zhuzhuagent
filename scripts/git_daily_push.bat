@echo off

setlocal

cd /d "%~dp0.."

set GIT_AUTHOR_NAME=zezeqq

set GIT_COMMITTER_NAME=zezeqq

set GIT_AUTHOR_EMAIL=1432450835@qq.com

set GIT_COMMITTER_EMAIL=1432450835@qq.com

if "%~1"=="" (

  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_push.ps1" -Auto

) else (

  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git_push.ps1" -Message "%*"

)

pause

