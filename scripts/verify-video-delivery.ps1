[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [string]$FfprobePath = "",
    [string]$FfmpegPath = "",
    # Require an AAC audio stream (use for voiced deliveries such as *.voiced.mp4).
    [switch]$RequireAudio,
    # Planned duration in seconds (render JSON duration_seconds); fails if off by more than -DurationTolerance.
    [double]$ExpectedDuration = 0,
    [double]$DurationTolerance = 0.25,
    [double]$ExpectedFps = 30,
    [double]$FreezeMaxSeconds = 0.8,
    [switch]$SkipFreezeCheck,
    # QA report path; default <video>.qa.json next to the video (never overwritten).
    [string]$QaJson = ""
)

# Thin wrapper around `tk-ops-workspace verify` (src/tk_ops_workspace/qa.py):
# H.264 1080x1920 yuv420p, fps, expected duration, optional AAC audio, freezedetect; writes a QA JSON.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
function Resolve-Full { param([string]$Path) return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }

$videoPath = Resolve-Full $Video
if (-not (Test-Path -LiteralPath $videoPath -PathType Leaf)) {
    throw "Video does not exist: $videoPath"
}
if ($null -eq (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required for delivery verification. Run scripts\bootstrap-video-editor-workspace.ps1 first."
}

$inv = [Globalization.CultureInfo]::InvariantCulture
$arguments = @(
    "run", "--project", $workspaceRoot, "tk-ops-workspace", "verify",
    "--video", $videoPath,
    "--duration-tolerance", $DurationTolerance.ToString($inv),
    "--expected-fps", $ExpectedFps.ToString($inv),
    "--freeze-max-seconds", $FreezeMaxSeconds.ToString($inv)
)
if ($ExpectedDuration -gt 0) { $arguments += @("--expected-duration", $ExpectedDuration.ToString($inv)) }
if ($RequireAudio) { $arguments += "--require-audio" }
if ($SkipFreezeCheck) { $arguments += "--skip-freeze-check" }
if ($QaJson) { $arguments += @("--qa-json", (Resolve-Full $QaJson)) }
if ($FfprobePath) { $arguments += @("--ffprobe", (Resolve-Full $FfprobePath)) }
if ($FfmpegPath) { $arguments += @("--ffmpeg", (Resolve-Full $FfmpegPath)) }

& uv @arguments
exit $LASTEXITCODE
