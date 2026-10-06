@echo off
setlocal
chcp 65001 >nul
rem 인덱스 웹뷰. 더블클릭하면 하네스가 최근에 돈 프로젝트로, 프로젝트 폴더를 이 파일 위에 끌어다 놓으면 그 프로젝트로 연다.
rem 브라우저가 자동으로 열린다. 이미 떠 있으면 새로 띄우지 않고 그것을 연다 (다른 프로젝트면 그 프로젝트로 바꾼다).
rem 끝내려면 이 창에서 Ctrl+C 또는 창을 닫는다.

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
if "%~1"=="" (
    %PY% "%~dp0skills\game-onboard\scripts\index_view.py" --open
) else (
    %PY% "%~dp0skills\game-onboard\scripts\index_view.py" --open --root "%~1"
)
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
    echo.
    echo 아무 키나 누르면 닫힌다.
    pause >nul
)
exit /b %RC%
