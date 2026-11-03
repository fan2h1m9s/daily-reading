@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

if "%~1"=="" goto noarg
python prepare.py "%~1"
if errorlevel 1 goto fail
goto ok

:noarg
python prepare.py
if errorlevel 1 goto fail

:ok
echo.
pause
exit /b 0

:fail
echo.
echo   转换没成功，看上面的报错。
pause
exit /b 1

:nopython
echo.
echo   [x] 未检测到 Python，请先安装: https://www.python.org
echo       安装时记得勾选 "Add python.exe to PATH"
pause
exit /b 1
