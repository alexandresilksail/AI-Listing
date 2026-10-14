@echo off
chcp 65001 >nul
echo ============================================
echo  PolyListing AI 启动脚本（Windows 开发环境）
echo ============================================

echo [1/3] 检查后端 Python 环境...
if exist ".venv\Scripts\python.exe" (
    set PY=.venv\Scripts\python.exe
) else if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\polylisting\Scripts\python.exe" (
    set PY=%USERPROFILE%\.workbuddy\binaries\python\envs\polylisting\Scripts\python.exe
) else (
    set PY=python
)

echo [2/3] 启动后端 http://127.0.0.1:8000 ...
start "PolyListing Backend" cmd /k "cd /d %~dp0backend && %PY% -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

echo [3/3] 启动前端 http://127.0.0.1:5173 ...
start "PolyListing Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:5173
echo 已在浏览器打开 http://127.0.0.1:5173
pause
