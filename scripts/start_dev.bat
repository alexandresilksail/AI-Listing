@echo off
chcp 65001 >nul
echo ============================================================
echo  PolyListing AI 一键启动（Windows）
echo  首次运行会自动创建 Python 虚拟环境并安装依赖，请耐心等待
echo ============================================================

set PROJECT_DIR=%~dp0
set BACKEND_DIR=%PROJECT_DIR%backend
set FRONTEND_DIR=%PROJECT_DIR%frontend
set VENV_DIR=%PROJECT_DIR%.venv

REM ---------- [1/5] 检查 Python ----------
echo [1/5] 检查 Python 环境...
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python 命令。请先安装 Python 3.10+：
    echo   https://www.python.org/downloads/ （安装时勾选 Add to PATH）
    pause
    exit /b 1
)

REM ---------- [2/5] 创建/校验虚拟环境并安装后端依赖 ----------
echo [2/5] 准备后端 Python 环境...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo   首次运行：创建虚拟环境 %VENV_DIR% ...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。请确认 Python 版本 3.10+ 且 venv 模块可用。
        pause
        exit /b 1
    )
)
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [错误] 虚拟环境不可用：%VENV_DIR%\Scripts\python.exe
    pause
    exit /b 1
)
echo   安装/校验后端依赖...
"%VENV_DIR%\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r "%BACKEND_DIR%\requirements.txt"
if errorlevel 1 (
    echo [错误] 后端依赖安装失败。请检查网络后重试，或手动执行：
    echo   "%VENV_DIR%\Scripts\python.exe" -m pip install -r "%BACKEND_DIR%\requirements.txt"
    pause
    exit /b 1
)

REM ---------- [3/5] 安装前端依赖 ----------
echo [3/5] 准备前端环境...
where npm >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 npm。请先安装 Node.js 20+：
    echo   https://nodejs.org/ （LTS 版本，安装时勾选 Add to PATH）
    pause
    exit /b 1
)
if not exist "%FRONTEND_DIR%\node_modules\" (
    echo   首次运行：安装前端依赖（耗时较久）...
    cd /d "%FRONTEND_DIR%"
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败。请检查网络后重试。
        pause
        exit /b 1
    )
)

REM ---------- [4/5] 启动后端 ----------
echo [4/5] 启动后端 http://127.0.0.1:8000 ...
start "PolyListing Backend" cmd /k "cd /d %BACKEND_DIR% && %VENV_DIR%\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM 等待后端就绪（最多 30 秒）
echo   等待后端就绪...
set /a _tries=0
:wait_backend
set /a _tries+=1
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/health | findstr /r "^[25]" >nul 2>nul
if not errorlevel 1 (
    echo   后端已就绪。
    goto backend_ok
)
if %_tries% GEQ 15 (
    echo   [警告] 后端 30 秒内未就绪，请查看 "PolyListing Backend" 窗口的错误信息。
    goto backend_ok
)
goto wait_backend
:backend_ok

REM ---------- [5/5] 启动前端 ----------
echo [5/5] 启动前端 http://127.0.0.1:5173 ...
start "PolyListing Frontend" cmd /k "cd /d %FRONTEND_DIR% && npm run dev"

timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:5173
echo.
echo ============================================================
echo  已启动：
echo    前端   http://127.0.0.1:5173
echo    后端   http://127.0.0.1:8000/api/health
echo  未配置模型 API 时为模拟演示模式（结果明确标记，禁止直接发布）
echo ============================================================
pause
