@echo off
chcp 65001 >nul
setlocal

echo Starting Zhulong with model services
echo ============================================
echo.

if not exist "zhulong\package.json" (
    echo [ERROR] Frontend directory was not found.
    pause
    exit /b 1
)

cd /d "%~dp0zhulong"

if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Frontend dependency installation failed.
        pause
        exit /b 1
    )
)

echo Starting model services and frontend...
echo Frontend: http://127.0.0.1:3000/#/login
echo Unified media API: http://127.0.0.1:5002
echo AI image detector: http://127.0.0.1:5004
echo Deepfake video detector: http://127.0.0.1:5003
echo.
echo Keep this window open while using the app.
echo The browser will open automatically when the frontend is ready.
echo.

call npm run dev

pause
