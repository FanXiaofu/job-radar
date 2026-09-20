@echo off
setlocal
pushd "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "E:\AIProject\environment\job-radar-venv\Scripts\python.exe" set "PY=E:\AIProject\environment\job-radar-venv\Scripts\python.exe"

if not defined PY goto nopy

echo ============================================
echo   JobRadar - starting web server
echo   Open in browser: http://127.0.0.1:8000
echo   Press Ctrl+C to stop
echo ============================================
echo.
"%PY%" main.py serve
echo.
echo Server stopped.
pause
goto end

:nopy
echo [ERROR] Python venv not found.
echo.
echo Create it first:
echo   python -m venv E:\AIProject\environment\job-radar-venv
echo   E:\AIProject\environment\job-radar-venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
pause

:end
popd
endlocal
