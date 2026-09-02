param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [int]$FirstIndex = 11,
    [int]$LastIndex = 30
)

$ErrorActionPreference = 'Stop'
$validationRoot = Join-Path $ProjectRoot 'eval/videos_validation'
$realRoot = Join-Path $validationRoot 'real'
$fakeRoot = Join-Path $validationRoot 'deepfake'
New-Item -ItemType Directory -Force -Path $realRoot, $fakeRoot | Out-Null

function Save-ValidationVideo {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Target
    )
    if (Test-Path -LiteralPath $Target) {
        Write-Host "Exists: $Target"
        return
    }
    Invoke-WebRequest -Uri $Url -OutFile $Target -UseBasicParsing -TimeoutSec 120
    if ((Get-Item -LiteralPath $Target).Length -lt 1024) {
        Remove-Item -LiteralPath $Target -Force
        throw "Downloaded file is unexpectedly small: $Target"
    }
}

foreach ($index in $FirstIndex..$LastIndex) {
    $number = '{0:D2}' -f $index
    Save-ValidationVideo `
        -Url "https://huggingface.co/datasets/Hemgg/SDFVD-video-dataset/resolve/main/Real/v$index.mp4?download=true" `
        -Target (Join-Path $realRoot "sdfvd_real_$number.mp4")
    Save-ValidationVideo `
        -Url "https://huggingface.co/datasets/Hemgg/SDFVD-video-dataset/resolve/main/Fake/vs$index.mp4?download=true" `
        -Target (Join-Path $fakeRoot "sdfvd_fake_$number.mp4")
}

Write-Host "Independent validation videos are ready: $FirstIndex..$LastIndex"
