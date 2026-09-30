@echo off
setlocal
rem game-harness installer. Double-click = copy install.
rem Arguments are passed to install.py as-is: --link, --force, --dry-run

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    if "%~1"=="" pause
    exit /b 1
)

set PYTHONIOENCODING=utf-8
%PY% "%~dp0install.py" %*
set RC=%ERRORLEVEL%

if "%~1"=="" pause
exit /b %RC%
