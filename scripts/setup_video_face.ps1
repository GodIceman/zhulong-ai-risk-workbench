param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))

$ErrorActionPreference = 'Stop'
$python = Join-Path $ProjectRoot '.venv-video-d3\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    uv venv (Join-Path $ProjectRoot '.venv-video-d3') --python 3.11
}

uv pip install --python $python torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python $python transformers==4.57.0 opencv-python-headless==4.12.0.88 numpy==2.2.6 flask==3.1.3 flask-cors==6.0.5 Werkzeug==3.1.8

& $python -c "import video_face_api as api; assert api.load_model(); print('LNCLIP video service is ready')"
