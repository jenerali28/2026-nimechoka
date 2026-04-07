@echo off
REM =============================================================================
REM Video Clone Pipeline — Master Orchestrator (Windows)
REM =============================================================================

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set GROK2API_DIR=%SCRIPT_DIR%grok2api
set AISTUDIO_DIR=%SCRIPT_DIR%AIStudio2API
set LOGS_DIR=%SCRIPT_DIR%logs

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

REM ---------------------------------------------------------------------------
REM 1. Kill existing instances
REM ---------------------------------------------------------------------------
echo [1/6] Stopping existing services...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM uvicorn.exe 2>nul

REM Kill processes on key ports
for %%p in (8000 9000 2048 3001 3002) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p " ^| findstr LISTENING') do (
        taskkill /F /PID %%a 2>nul
    )
)

timeout /t 2 /nobreak >nul

REM ---------------------------------------------------------------------------
REM 2. Start Grok2API
REM ---------------------------------------------------------------------------
echo [2/6] Starting Grok2API...
cd /d "%GROK2API_DIR%"

REM Check for uv
where uv >nul 2>&1
if %errorlevel% == 0 (
    start "Grok2API" /min cmd /c "uv run python main.py > "%LOGS_DIR%\grok2api.log" 2>&1"
) else (
    start "Grok2API" /min cmd /c "python main.py > "%LOGS_DIR%\grok2api.log" 2>&1"
)

cd /d "%SCRIPT_DIR%"

REM ---------------------------------------------------------------------------
REM 3. Start AIStudio2API
REM ---------------------------------------------------------------------------
echo [3/6] Starting AIStudio2API...
cd /d "%AISTUDIO_DIR%"

if not exist "data" mkdir data

REM Write gui_config.json
(
echo {
echo   "fastapi_port": 2048,
echo   "camoufox_debug_port": 9222,
echo   "stream_port": 3120,
echo   "stream_port_enabled": true,
echo   "proxy_enabled": false,
echo   "proxy_address": "",
echo   "helper_enabled": false,
echo   "helper_endpoint": "",
echo   "launch_mode": "headless",
echo   "script_injection_enabled": false,
echo   "worker_mode_enabled": true,
echo   "log_enabled": true
echo }
) > "data\gui_config.json"

set PYTHONPATH=src
start "AIStudio2API" /min cmd /c "uv run python src\app_launcher.py > "%LOGS_DIR%\aistudio.log" 2>&1"

cd /d "%SCRIPT_DIR%"

REM ---------------------------------------------------------------------------
REM 4. Wait for services
REM ---------------------------------------------------------------------------
echo [4/6] Waiting 45s for services to initialize...
timeout /t 45 /nobreak >nul

REM Health checks
echo [4/6] Checking services...
curl -sf http://localhost:8000/v1/models >nul 2>&1
if %errorlevel% == 0 (
    echo   OK Grok2API is running
) else (
    echo   WARN Grok2API not responding - check logs\grok2api.log
)

curl -sf http://localhost:2048/health >nul 2>&1
if %errorlevel% == 0 (
    echo   OK AIStudio2API is running
    REM Trigger worker start
    curl -s -X POST http://127.0.0.1:9000/api/control/start -H "Content-Type: application/json" -d @"%AISTUDIO_DIR%\data\gui_config.json" >nul 2>&1
) else (
    echo   WARN AIStudio2API not responding - check logs\aistudio.log
)

REM ---------------------------------------------------------------------------
REM 5. Set environment variables
REM ---------------------------------------------------------------------------
set GROK_API_BASE=http://localhost:8000
set GROK_API_KEY=grok2api
set API_BASE_URL=http://localhost:2048

REM ---------------------------------------------------------------------------
REM 6. Run Bulk Pipeline
REM ---------------------------------------------------------------------------
echo [6/6] Launching Bulk Processor...

REM Detect venv python
if exist ".venv\Scripts\python.exe" (
    set VENV_PYTHON=.venv\Scripts\python.exe
) else (
    set VENV_PYTHON=python
)

%VENV_PYTHON% bulk_processor.py

echo Pipeline session finished.
pause
