@echo off
setlocal
rem game-harness project setup. Drag a project folder onto this file, or: bootstrap.bat <project> [--team] [--dry-run]
rem Creates CLAUDE.local.md (or CLAUDE.md with --team) and .claude/session_start.json. Never overwrites.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.10+ and add it to PATH.
    pause
    exit /b 1
)

set "TARGET=%~1"
if "%TARGET%"=="" set /p "TARGET=Project folder: "
if "%TARGET%"=="" exit /b 1

set PYTHONIOENCODING=utf-8
%PY% "%~dp0skills\game-bootstrap\scripts\bootstrap.py" "%TARGET%" %2 %3 %4 %5
set RC=%ERRORLEVEL%
pause
exit /b %RC%
