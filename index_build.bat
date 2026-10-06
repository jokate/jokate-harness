@echo off
setlocal
chcp 65001 >nul
rem 인덱스를 지금 만든다. 프로젝트 폴더를 이 파일 위에 끌어다 놓으면 그 프로젝트, 더블클릭하면 하네스가 최근에 돈 프로젝트로 한다.
rem 순서: 프로젝트 좌표(gq) - 엔진 좌표(ue_q) - compile_commands.json(없을 때만) - clangd 프로젝트(바뀐 것만) - clangd 엔진(없을 때만).
rem 명령 창에서는 옵션을 붙인다: index_build.bat [프로젝트 폴더] [--no-clangd] [--cdb] [--engine]
rem 엔진 폴더를 못 찾으면 먼저 set UE_ROOT=엔진 폴더 를 한다. 자세한 것은 skills\game-onboard\scripts\index_all.py 머리말.

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo [오류] Python 을 찾지 못했다. Python 3.10 이상을 설치하고 PATH 에 추가한다.
    echo 아무 키나 누르면 닫힌다.
    pause >nul
    exit /b 1
)

set PYTHONIOENCODING=utf-8
%PY% "%~dp0skills\game-onboard\scripts\index_all.py" %*
set RC=%ERRORLEVEL%
echo.
echo 아무 키나 누르면 닫힌다.
pause >nul
exit /b %RC%
