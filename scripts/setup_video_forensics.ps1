param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$IncludeWaveRepCandidate
)

$ErrorActionPreference = 'Stop'

$venv = Join-Path $ProjectRoot '.venv-video-forensics'
$python = Join-Path $venv 'Scripts\python.exe'
$waveRepRepo = Join-Path $ProjectRoot 'third_party\WaveRep-SyntheticVideoDetection'
$waveRepUrl = 'https://github.com/grip-unina/WaveRep-SyntheticVideoDetection.git'
$waveRepRevision = '0fd6010759c14b572b7842a28fa9f85fe1ddd2fd'
$aegisRepo = Join-Path $ProjectRoot 'third_party\AEGIS'
$aegisUrl = 'https://github.com/MusapYildiz/ai_video_detection_benchmark.git'
$aegisRevision = 'd86a774fd971954a023e1cd00ed7ff5b2575e0d1'
$d3Repo = Join-Path $ProjectRoot 'third_party\D3'
$d3Url = 'https://github.com/Zig-HS/D3.git'
$d3Revision = 'c798fbc57fe0c4198d63a73732c2c0f9e4b4816c'
$weightDirectory = Join-Path $ProjectRoot 'data\models\waverep'
$weightPath = Join-Path $weightDirectory 'weights_dinov2_G4.ckpt'
$weightUrl = 'https://www.grip.unina.it/download/prog/WaveRep_SynthVideoDet/weights_dinov2_G4.ckpt'
$expectedMd5 = '8bf19e6f68a92bed600dd97fbed3f2cd'

function Install-PinnedRepository {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Path,
        [string]$Revision
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
        git clone $Url $Path
        git -C $Path checkout --detach $Revision
    }

    $actualRevision = (git -C $Path rev-parse HEAD).Trim()
    if ($actualRevision -ne $Revision) {
        throw "$Name revision mismatch. Expected $Revision but found $actualRevision. Keep local changes safe, then restore the pinned revision manually."
    }
}

if (-not (Test-Path -LiteralPath $python)) {
    uv venv $venv --python 3.11
}

uv pip install --python $python torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python $python `
    transformers==4.57.6 `
    hf-xet==1.2.0 `
    timm==1.0.27 `
    einops==0.8.2 `
    opencv-python-headless==4.12.0.88 `
    numpy==2.2.6 `
    scipy==1.15.3 `
    scikit-learn==1.7.2 `
    pandas==2.3.3 `
    pillow==12.3.0 `
    flask==3.1.3 `
    flask-cors==6.0.5 `
    Werkzeug==3.1.8

Install-PinnedRepository -Name 'AEGIS' -Url $aegisUrl -Path $aegisRepo -Revision $aegisRevision
Install-PinnedRepository -Name 'D3' -Url $d3Url -Path $d3Repo -Revision $d3Revision

if ($IncludeWaveRepCandidate) {
    Install-PinnedRepository -Name 'WaveRep' -Url $waveRepUrl -Path $waveRepRepo -Revision $waveRepRevision
    New-Item -ItemType Directory -Force -Path $weightDirectory | Out-Null
    if (-not (Test-Path -LiteralPath $weightPath)) {
        Invoke-WebRequest -Uri $weightUrl -OutFile $weightPath
    }
    $actualMd5 = (Get-FileHash -LiteralPath $weightPath -Algorithm MD5).Hash.ToLowerInvariant()
    if ($actualMd5 -ne $expectedMd5) {
        throw "WaveRep weight checksum mismatch. Expected $expectedMd5 but found $actualMd5"
    }
    Write-Output "WaveRep G4 weights: $weightPath"
    Write-Output "WaveRep G4 SHA256: $((Get-FileHash -LiteralPath $weightPath -Algorithm SHA256).Hash.ToLowerInvariant())"
}

& $python (Join-Path $ProjectRoot 'scripts\download_aegis_checkpoint.py')
& $python -c "import torch, timm, transformers; print(f'torch={torch.__version__} cuda={torch.cuda.is_available()} timm={timm.__version__} transformers={transformers.__version__}')"
