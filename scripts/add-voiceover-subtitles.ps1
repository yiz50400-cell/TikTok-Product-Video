[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [Parameter(Mandatory = $true)]
    [string]$VoiceoverScript,
    [Parameter(Mandatory = $true)]
    [string]$RunDir,
    [Parameter(Mandatory = $true)]
    [string]$Market,
    [string]$Category = "general",
    [string]$Language = "",
    [string]$ApprovedBy = "",
    [ValidateSet("auto", "kokoro", "edge-tts", "silent")]
    [string]$TtsBackend = "auto",
    [string]$Voice = "",
    [double]$Speed = 1.0,
    [switch]$BurnSubtitles,
    [int]$SubtitleMarginV = 110,
    [string]$OutputStem = "",
    [switch]$AiGenerated,
    [switch]$AiLabelEnabled,
    [string]$FfmpegPath = "",
    [string]$FfprobePath = ""
)

# Voiceover + phrase-synced SRT + AAC mux for an already approved, localized script.
# Blocks (exit 2) when the script is not approved or fails video-compliance. Never overwrites outputs.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$bundledBin = Join-Path $workspaceRoot ".tools\bin"
if (-not $FfmpegPath -and (Test-Path -LiteralPath (Join-Path $bundledBin "ffmpeg.exe"))) { $FfmpegPath = Join-Path $bundledBin "ffmpeg.exe" }
if (-not $FfprobePath -and (Test-Path -LiteralPath (Join-Path $bundledBin "ffprobe.exe"))) { $FfprobePath = Join-Path $bundledBin "ffprobe.exe" }

function Resolve-Full { param([string]$Path) return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }

$arguments = @(
    "run", "--project", $workspaceRoot, "tk-ops-workspace", "voiceover", "build",
    "--video", (Resolve-Full $Video),
    "--script", (Resolve-Full $VoiceoverScript),
    "--run-dir", (Resolve-Full $RunDir),
    "--market", $Market,
    "--category", $Category,
    "--backend", $TtsBackend,
    "--speed", $Speed.ToString([Globalization.CultureInfo]::InvariantCulture),
    "--subtitle-margin-v", "$SubtitleMarginV"
)
if ($Language) { $arguments += @("--language", $Language) }
if ($ApprovedBy) { $arguments += @("--approved-by", $ApprovedBy) }
if ($Voice) { $arguments += @("--voice", $Voice) }
if ($OutputStem) { $arguments += @("--output-stem", $OutputStem) }
if ($BurnSubtitles) { $arguments += "--burn-subtitles" }
if ($AiGenerated) { $arguments += "--ai-generated" }
if ($AiLabelEnabled) { $arguments += "--ai-label-enabled" }
if ($FfmpegPath) { $arguments += @("--ffmpeg", (Resolve-Full $FfmpegPath)) }
if ($FfprobePath) { $arguments += @("--ffprobe", (Resolve-Full $FfprobePath)) }

& uv @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Voiceover step blocked or failed (exit $LASTEXITCODE). See JSON above; fix approval/compliance/TTS, then use a new run directory."
}
