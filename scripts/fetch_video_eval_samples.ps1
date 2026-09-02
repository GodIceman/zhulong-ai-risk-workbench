param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$videoRoot = Join-Path $ProjectRoot 'eval/videos'

foreach ($name in @('real', 'deepfake', 'generated')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $videoRoot $name) | Out-Null
}

function Save-EvalVideo {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $target = Join-Path $ProjectRoot $RelativePath
    if (Test-Path $target) {
        Write-Host "Exists: $RelativePath"
        return
    }

    Write-Host "Downloading: $RelativePath"
    Invoke-WebRequest -Uri $Url -OutFile $target -UseBasicParsing -TimeoutSec 120
    if ((Get-Item $target).Length -lt 1024) {
        Remove-Item -LiteralPath $target -Force
        throw "Downloaded file is unexpectedly small: $RelativePath"
    }
}

foreach ($index in 1..10) {
    $number = '{0:D2}' -f $index
    Save-EvalVideo `
        -Url "https://huggingface.co/datasets/Hemgg/SDFVD-video-dataset/resolve/main/Real/v$index.mp4?download=true" `
        -RelativePath "eval/videos/real/sdfvd_real_$number.mp4"
    Save-EvalVideo `
        -Url "https://huggingface.co/datasets/Hemgg/SDFVD-video-dataset/resolve/main/Fake/vs$index.mp4?download=true" `
        -RelativePath "eval/videos/deepfake/sdfvd_fake_$number.mp4"
}

$cogVideoPaths = @(
    'inference/gradio_composite_demo/example_videos/horse.mp4',
    'inference/gradio_composite_demo/example_videos/kitten.mp4',
    'inference/gradio_composite_demo/example_videos/train_running.mp4',
    'resources/videos/1.mp4',
    'resources/videos/2.mp4',
    'resources/videos/3.mp4',
    'resources/videos/4.mp4'
)

for ($index = 0; $index -lt $cogVideoPaths.Count; $index++) {
    $number = '{0:D2}' -f ($index + 1)
    Save-EvalVideo `
        -Url "https://raw.githubusercontent.com/THUDM/CogVideo/main/$($cogVideoPaths[$index])" `
        -RelativePath "eval/videos/generated/cogvideo_$number.mp4"
}

$text2VideoZeroFiles = @('camel.mp4', 'mini-cooper.mp4', 'snowboard.mp4', 'white-swan.mp4')
for ($index = 0; $index -lt $text2VideoZeroFiles.Count; $index++) {
    $number = '{0:D2}' -f ($index + 1)
    $file = $text2VideoZeroFiles[$index]
    Save-EvalVideo `
        -Url "https://raw.githubusercontent.com/Picsart-AI-Research/Text2Video-Zero/main/__assets__/pix2pix%20video/$file" `
        -RelativePath "eval/videos/generated/text2videozero_$number.mp4"
}

Save-EvalVideo `
    -Url 'https://raw.githubusercontent.com/genmoai/models/main/assets/grid.mp4' `
    -RelativePath 'eval/videos/generated/mochi_01.mp4'

Write-Host 'Video evaluation samples are ready.'
