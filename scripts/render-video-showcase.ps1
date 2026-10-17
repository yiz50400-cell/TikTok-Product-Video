[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$RunDir,
    [string]$SegmentsJson = "",
    [string]$Title = "",
    [string]$Cta = "",
    [string]$OutputName = "showcase.mp4",
    [string]$ArrowPath = "",
    [string]$CartPath = "",
    [string]$FfmpegPath = "",
    [string]$FfprobePath = "",
    # Optional voiceover/subtitle step (omit -VoiceoverScript for the original visual-only render).
    [string]$VoiceoverScript = "",
    [string]$Market = "",
    [string]$Category = "general",
    [string]$Language = "",
    [string]$ApprovedBy = "",
    [ValidateSet("auto", "kokoro", "edge-tts", "silent")]
    [string]$TtsBackend = "auto",
    [string]$Voice = "",
    [double]$Speed = 1.0,
    [switch]$BurnSubtitles
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$sourcePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Source)
$runPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($RunDir)
if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Source video does not exist: $sourcePath"
}
if ($VoiceoverScript -and -not $Market) {
    throw "-Market is required when -VoiceoverScript is given."
}
New-Item -ItemType Directory -Force -Path $runPath | Out-Null

function Resolve-ToolPath {
    param([string]$Requested, [string]$BundledName, [string]$CommandName)
    if ($Requested) {
        $resolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Requested)
        if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
            throw "Tool does not exist: $resolved"
        }
        return $resolved
    }
    $bundled = Join-Path $workspaceRoot ".tools\bin\$BundledName"
    if (Test-Path -LiteralPath $bundled -PathType Leaf) { return $bundled }
    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Missing $CommandName. Install FFmpeg or pass the matching path parameter."
    }
    return $command.Source
}

function Number {
    param([double]$Value)
    return $Value.ToString("0.###", [Globalization.CultureInfo]::InvariantCulture)
}

function Invoke-Ffmpeg {
    param([string[]]$Arguments)
    & $script:ffmpeg @Arguments
    if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed with exit code $LASTEXITCODE." }
}

function FilterPath {
    param([string]$Path)
    return $Path.Replace("\", "/").Replace(":", "\:")
}

$ffmpeg = Resolve-ToolPath $FfmpegPath "ffmpeg.exe" "ffmpeg"
$ffprobe = Resolve-ToolPath $FfprobePath "ffprobe.exe" "ffprobe"
if (-not $SegmentsJson) {
    $SegmentsJson = Join-Path $workspaceRoot "config\video-showcase.example.json"
}
$segmentsPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($SegmentsJson)
if (-not (Test-Path -LiteralPath $segmentsPath -PathType Leaf)) {
    throw "Segments JSON does not exist: $segmentsPath"
}

$plan = Get-Content -Raw -LiteralPath $segmentsPath | ConvertFrom-Json
$segments = @($plan.segments)
if ($segments.Count -eq 0) { throw "Segments JSON must contain at least one segment." }
if (-not $Title) { $Title = [string]$plan.title }
if (-not $Cta) { $Cta = [string]$plan.cta }
if (-not $Title) { $Title = "Producto destacado" }
if (-not $Cta) { $Cta = "P\u00eddelo en el carrito" }

if (-not $ArrowPath) {
    $ArrowPath = Join-Path $workspaceRoot "assets\video\overlays\preferred_down_arrow.png"
}
if (-not $CartPath) {
    $CartPath = Join-Path $workspaceRoot "assets\video\overlays\preferred_cart.png"
}
$arrowPathResolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ArrowPath)
$cartPathResolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($CartPath)
foreach ($asset in @($arrowPathResolved, $cartPathResolved)) {
    if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) {
        throw "Overlay asset does not exist: $asset"
    }
}

$workPath = Join-Path $runPath "work"
$outputPath = Join-Path $runPath $OutputName
$titleFile = Join-Path $workPath "title.txt"
$ctaFile = Join-Path $workPath "cta.txt"
$probePath = Join-Path $runPath "ffprobe.json"
if (Test-Path -LiteralPath $outputPath) {
    throw "Output already exists: $outputPath. Use a new -RunDir; previous runs are never overwritten."
}
New-Item -ItemType Directory -Force -Path $workPath | Out-Null
[System.IO.File]::WriteAllText($titleFile, $Title, $utf8NoBom)
[System.IO.File]::WriteAllText($ctaFile, $Cta, $utf8NoBom)

$graph = New-Object System.Collections.Generic.List[string]
$labels = New-Object System.Collections.Generic.List[string]
$totalDuration = 0.0
for ($i = 0; $i -lt $segments.Count; $i++) {
    $segment = $segments[$i]
    $start = [double]$segment.start
    $end = [double]$segment.end
    $speed = [double]$segment.speed
    if ($end -le $start -or $speed -le 0) {
        throw "Invalid segment at index $i. Require end > start and speed > 0."
    }
    $totalDuration += ($end - $start) / $speed
    $label = "v$i"
    $labels.Add("[$label]")
    $graph.Add("[0:v]trim=start=$(Number $start):end=$(Number $end),setpts=(PTS-STARTPTS)/$(Number $speed),scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[$label];")
}

$totalDuration = [math]::Round($totalDuration, 3)
$ctaStart = [math]::Round([math]::Max(0, $totalDuration - 3.0), 3)
$graph.Add((($labels -join "") + "concat=n=$($segments.Count):v=1:a=0[base];"))
$graph.Add("[base]drawtext=textfile='$(FilterPath $titleFile)':enable='between(t,0,3)':x=(w-text_w)/2:y=245:fontsize=52:fontcolor=white:borderw=4:bordercolor=black@0.6:box=1:boxcolor=black@0.35:boxborderw=18[t1];")
$graph.Add("[t1]drawtext=textfile='$(FilterPath $ctaFile)':enable='gte(t,$(Number $ctaStart))':x=(w-text_w)/2:y=245:fontsize=50:fontcolor=white:borderw=4:bordercolor=black@0.6:box=1:boxcolor=black@0.35:boxborderw=18[t2];")
$graph.Add("[1:v]format=rgba,scale=180:-1,trim=duration=$(Number $totalDuration),setpts=PTS-STARTPTS[ar];")
$graph.Add("[2:v]format=rgba,scale=175:-1,trim=duration=$(Number $totalDuration),setpts=PTS-STARTPTS[ca];")
$graph.Add("[t2][ar]overlay=x=165:y='1245+42*sin(2*PI*t/0.72)':enable='gte(t,$(Number $ctaStart))'[u];")
$graph.Add("[u][ca]overlay=x=365:y=1320:enable='gte(t,$(Number $ctaStart))'[v]")

Invoke-Ffmpeg @(
    "-n", "-hide_banner", "-loglevel", "error",
    "-i", $sourcePath,
    "-loop", "1", "-i", $arrowPathResolved,
    "-loop", "1", "-i", $cartPathResolved,
    "-filter_complex", ($graph -join "`n"),
    "-map", "[v]", "-an", "-t", (Number $totalDuration),
    "-r", "30", "-c:v", "libx264", "-crf", "21",
    "-pix_fmt", "yuv420p", "-movflags", "+faststart", $outputPath
)

& $ffprobe "-v" "error" "-show_entries" "format=duration:stream=codec_name,width,height,pix_fmt,r_frame_rate" "-of" "json" $outputPath | Set-Content -LiteralPath $probePath -Encoding utf8
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "Render output verification failed."
}

$voiceover = $null
if ($VoiceoverScript) {
    $voArgs = @{
        Video = $outputPath; VoiceoverScript = $VoiceoverScript; RunDir = $runPath
        Market = $Market; Category = $Category; TtsBackend = $TtsBackend; Speed = $Speed
        FfmpegPath = $ffmpeg; FfprobePath = $ffprobe
    }
    if ($Language) { $voArgs.Language = $Language }
    if ($ApprovedBy) { $voArgs.ApprovedBy = $ApprovedBy }
    if ($Voice) { $voArgs.Voice = $Voice }
    if ($BurnSubtitles) { $voArgs.BurnSubtitles = $true }
    $voiceoverJson = & (Join-Path $PSScriptRoot "add-voiceover-subtitles.ps1") @voArgs
    $voiceover = ($voiceoverJson -join "`n") | ConvertFrom-Json
}

[pscustomobject]@{
    output = $outputPath
    voiceover = $voiceover
    ffprobe = $probePath
    duration_seconds = $totalDuration
    segment_count = $segments.Count
    title = $Title
    cta = $Cta
} | ConvertTo-Json -Depth 4
