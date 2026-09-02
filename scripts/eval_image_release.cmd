@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON=.venv-modern\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=.venv-lrfimd\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Python environment not found. Run scripts\setup_venv.cmd first.
  exit /b 2
)

"%PYTHON%" scripts\eval_media_detection.py ^
  --output logs\eval\latest.csv ^
  --summary-output logs\eval\latest.md ^
  --release-gate ^
  --min-ai-clear-detection-rate 0.50 ^
  --min-ai-non-metadata-clear-rate 0.50 ^
  --max-overall-uncertain-rate 0.50 ^
  --max-ai-uncertain-rate 0.50 ^
  --max-real-uncertain-rate 0.50 ^
  --strict %*

exit /b %ERRORLEVEL%
