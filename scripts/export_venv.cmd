@echo off
setlocal
pushd "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\export_venv.ps1"
set RC=%ERRORLEVEL%
popd
exit /b %RC%
