@echo off
chcp 65001 >nul
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo [x] 未检测到 Node.js，请先安装: https://nodejs.org
  pause & exit /b 1
)

if not exist article.json (
  echo [x] 还没有 article.json，先运行 1-提取PDF.bat
  pause & exit /b 1
)

node server.js
pause
