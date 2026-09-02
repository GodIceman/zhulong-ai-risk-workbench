$ErrorActionPreference = 'Stop'

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $projectRoot

if (-not $env:VIRTUAL_ENV) {
    Write-Error "No active virtual environment detected. Please activate your venv first."
    exit 1
}

$venvPath = $env:VIRTUAL_ENV
$venvName = Split-Path -Leaf $venvPath

"$venvName" | Out-File -Encoding ascii -NoNewline .\.venv-name

Write-Host "Exporting dependencies from venv '$venvName'..."

$pythonExe = Join-Path $venvPath 'Scripts/python.exe'
if (-not (Test-Path $pythonExe)) {
    Write-Error "Python executable not found in venv: $pythonExe"
    exit 1
}

& $pythonExe -m pip freeze | Out-File -Encoding ascii .\requirements.txt

Write-Host "Wrote .venv-name and requirements.txt"
