[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ArtifactDir,
    [string[]]$Languages = @("es-MX", "pt-BR", "id-ID"),
    [ValidateSet("edge-tts", "kokoro", "silent")]
    [string]$TtsBackend = "edge-tts",
    [string]$RunPrefix = "edge"
)

# End-to-end Windows verification: render + voiceover + burned subtitles in a work directory
# whose path contains Chinese characters and spaces, default font resolution (no -FontFile).
# Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less scripts as ANSI.
# Non-ASCII content (title, CTA, scripts) comes from UTF-8 fixtures in tests/e2e.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$fixtures = Join-Path $root "tests\e2e"
$market = @{ "es-MX" = "Mexico"; "pt-BR" = "Brazil"; "id-ID" = "Indonesia" }

# CJK "verification directory" name built from code points to stay ASCII here.
$cjk = -join [char[]](0x9A8C, 0x8BC1)
$cjk2 = -join [char[]](0x76EE, 0x5F55)
$work = Join-Path $env:RUNNER_TEMP ("$cjk $cjk2 e2e")
New-Item -ItemType Directory -Force -Path $work | Out-Null
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null

$plan = Join-Path $work ("plan " + $cjk + ".json")
Copy-Item -LiteralPath (Join-Path $fixtures "plan.json") -Destination $plan -Force
$planData = [System.IO.File]::ReadAllText($plan, $utf8NoBom) | ConvertFrom-Json

# Synthetic source with a visible "product" (white tube + cap) moving over testsrc2.
$source = Join-Path $work ("source " + $cjk + ".mp4")
if (-not (Test-Path -LiteralPath $source)) {
    $filter = "drawbox=x='420+120*sin(t)':y=260:w=440:h=200:color=white@1:t=fill," +
              "drawbox=x='860+120*sin(t)':y=300:w=90:h=120:color=red@1:t=fill"
    & ffmpeg -loglevel error -f lavfi -i "testsrc2=s=1280x720:d=37:r=30" -vf $filter -c:v libx264 -pix_fmt yuv420p $source
    if ($LASTEXITCODE -ne 0) { throw "source generation failed" }
}

$summary = [System.Collections.Generic.List[object]]::new()
foreach ($lang in $Languages) {
    $runDir = Join-Path $work ("$RunPrefix-$lang " + $cjk)
    $vo = Join-Path $work ("vo $lang " + $cjk + ".txt")
    Copy-Item -LiteralPath (Join-Path $fixtures "vo.$lang.txt") -Destination $vo -Force
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $json = & (Join-Path $root "scripts\render-video-showcase.ps1") -Source $source -RunDir $runDir `
        -SegmentsJson $plan -VoiceoverScript $vo -Market $market[$lang] -Language $lang `
        -ApprovedBy "ci-e2e" -TtsBackend $TtsBackend -BurnSubtitles
    $sw.Stop()
    $result = ($json -join "`n") | ConvertFrom-Json
    $voiced = Join-Path $runDir "showcase.voiced.subtitled.mp4"
    if (-not (Test-Path -LiteralPath $voiced)) { throw "missing $voiced" }
    & (Join-Path $root "scripts\verify-video-delivery.ps1") -Video $voiced -RequireAudio `
        -ExpectedDuration $result.duration_seconds -QaJson (Join-Path $runDir "verify-final.qa.json")
    if ($LASTEXITCODE -ne 0) { throw "verify failed for $lang" }

    $dest = Join-Path $ArtifactDir "$RunPrefix-$lang"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Get-ChildItem -LiteralPath $runDir -File | Where-Object { $_.Extension -in ".mp4", ".srt", ".json", ".wav" } |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $dest }
    $total = [double]$result.duration_seconds
    $times = @{ "title" = 1.5; "mid" = [math]::Round($total / 2, 2); "cta" = [math]::Round($total - 1.2, 2) }
    foreach ($name in $times.Keys) {
        $png = Join-Path $dest ("frame-$name.png")
        & ffmpeg -loglevel error -y -i $voiced -ss ($times[$name].ToString([Globalization.CultureInfo]::InvariantCulture)) -frames:v 1 $png
        if ($LASTEXITCODE -ne 0) { throw "frame extraction failed" }
    }
    $summary.Add([pscustomobject]@{
        language = $lang
        backend = $TtsBackend
        seconds = [math]::Round($sw.Elapsed.TotalSeconds, 1)
        fontfile = $result.fontfile
        title_font_size = $result.title_font_size
        title_lines = $result.title_lines
        render_warnings = $result.warnings
        voiceover_status = $result.voiceover.status
        work_dir = $runDir
    }) | Out-Null
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $ArtifactDir "summary-$RunPrefix.json") -Encoding UTF8
$summary | ConvertTo-Json -Depth 5
