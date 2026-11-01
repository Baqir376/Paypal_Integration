@echo off
setlocal enabledelayedexpansion

title Salix Multilingual Offline Demo Launcher

echo ==========================================================
echo   SALIX -- MULTILINGUAL OFFLINE DEMO LAUNCHER
echo   English ^| Urdu (Nastaliq) ^| Roman Urdu
echo   Mode: 100%% OFFLINE (Hermetic Mock Inference)
echo ==========================================================

cd /d "%~dp0"

:: 1. Force offline mock environment variables
set SALIX_PROVIDER_MODE=mock
set SALIX_API_URL=http://127.0.0.1:8010
set PORT=3000

:: 2. Check Python venv
if not exist "api\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at api\.venv\Scripts\python.exe
    pause
    exit /b 1
)

:: 3. Start Backend in a separate window
echo [*] Starting FastAPI Backend on port 8010 (Mock Mode)...
start "Salix API (Offline Backend)" cmd /k "cd /d "%~dp0api" && set SALIX_PROVIDER_MODE=mock && .venv\Scripts\python.exe -m uvicorn salix.app:app --host 127.0.0.1 --port 8010"

:: Wait 3 seconds for backend initialization
timeout /t 3 /nobreak >nul

:: 4. Start Next.js Frontend
echo [*] Starting Next.js Web Frontend on port 3000...
if exist "web\.next" (
    start "Salix Web (Frontend)" cmd /k "cd /d "%~dp0web" && npm run start -- -p 3000"
) else (
    start "Salix Web (Frontend)" cmd /k "cd /d "%~dp0web" && npm run dev -- -p 3000"
)

:: Wait 3 seconds and launch browser
timeout /t 3 /nobreak >nul
echo [*] Opening Browser to http://localhost:3000 ...
start http://localhost:3000

echo ==========================================================
echo   SALIX DEMO IS RUNNING!
echo   Web UI:   http://localhost:3000
echo   API:      http://127.0.0.1:8010/api
echo   Samples:  %~dp0storage\samples\
echo ==========================================================
echo.
echo Leave the open command windows running during your presentation.
echo Close those windows when you want to stop the demo.
echo.
pause
