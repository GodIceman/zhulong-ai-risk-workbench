@echo off
setlocal
pushd "%~dp0.."
if not defined VENV_NAME set VENV_NAME=.venv-lrfimd
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup_venv.ps1" -VenvName "%VENV_NAME%"
set RC=%ERRORLEVEL%
popd
exit /b %RC%
