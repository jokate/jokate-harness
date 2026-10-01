@echo off
setlocal
chcp 65001 >nul
rem 제거. 더블클릭하거나 프로젝트 폴더를 이 파일 위에 끌어다 놓는다. 하는 일은 uninstall.py 참고.

cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    echo [오류] Python 을 찾지 못했다. Python 3.10 이상을 설치하고 PATH 에 추가한다.
    echo 아무 키나 누르면 닫힌다.
    pause >nul
    exit /b 1
)

%PY% "%~dp0uninstall.py" %*
exit /b %ERRORLEVEL%
