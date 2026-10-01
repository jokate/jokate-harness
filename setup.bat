@echo off
setlocal
rem game-harness one-shot setup. Double-click, or drag a project folder onto this file.
rem   1) installs skills + hooks into %USERPROFILE%\.claude and registers hooks in settings.json (backup: settings.json.bak)
rem   2) sets up the project folder (CLAUDE.local.md + .claude\session_start.json, never overwrites)
rem   3) prints how to use it
rem Safe to run again: already-installed parts are skipped.

cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)
set PYTHONIOENCODING=utf-8

echo [1/2] Install (skills, hooks, settings)
%PY% "%~dp0install.py" --link --force --apply-settings
if errorlevel 1 (
    echo [ERROR] install failed.
    pause
    exit /b 1
)

echo.
echo [2/2] Project setup
set "TARGET=%~1"
if "%TARGET%"=="" (
    echo Type or drag your game project folder here, then press Enter.
    echo ^(the folder that has .uproject, or Assets + ProjectSettings. Empty = skip^)
    set /p "TARGET=Project folder: "
)
if "%TARGET%"=="" (
    echo Skipped. Later: drag a project folder onto setup.bat.
    pause
    exit /b 0
)
set TARGET=%TARGET:"=%

%PY% "%~dp0skills\game-bootstrap\scripts\bootstrap.py" "%TARGET%" --auto
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
