@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Zhulong AI verification startup
echo ===============================
echo.

echo Checking Node.js...
node --version
if errorlevel 1 (
    echo [ERROR] Node.js was not found. Please install Node.js 16+.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
)

echo.
echo Starting model services and frontend...
echo Frontend: http://127.0.0.1:3000/#/login
echo Unified media API: http://127.0.0.1:5002
echo AI image detector: http://127.0.0.1:5004
echo Deepfake video detector: http://127.0.0.1:5003
echo.
echo The browser will open automatically when the frontend is ready.
echo.

call npm run dev

pause
