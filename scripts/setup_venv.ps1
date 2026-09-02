param(
    [string]$VenvName = '.venv-lrfimd'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $projectRoot

if (-not (Test-Path '.\\requirements.txt')) {
    Write-Error "requirements.txt not found. Run scripts/export_venv.ps1 first."
    exit 1
}

if (-not $VenvName) {
    $VenvName = '.venv-lrfimd'
}

Write-Host "Creating virtual environment: $VenvName"

$python = 'python'
& $python -m venv $VenvName

$activateScript = Join-Path $projectRoot (Join-Path $VenvName 'Scripts/Activate.ps1')
if (-not (Test-Path $activateScript)) {
    Write-Error "Activation script not found: $activateScript"
    exit 1
}

. $activateScript

Write-Host "Upgrading pip and wheel..."
python -m pip install --upgrade pip wheel setuptools

Write-Host "Installing dependencies from requirements.txt..."
python -m pip install -r .\\requirements.txt

Write-Host "Venv ready: $VenvName"
