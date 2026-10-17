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
    # Explicit TTF/OTF for title/CTA text (default: layout.fontfile, $env:TK_VIDEO_FONTFILE, then Arial Bold / Segoe UI Bold).
    [string]$FontFile = "",
    [switch]$SkipQa,
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

# Thin Windows wrapper. Validation, layout, filter graph and QA live in
# src/tk_ops_workspace/render.py (`tk-ops-workspace render showcase`).

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
function Resolve-Full { param([string]$Path) return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path) }

function ConvertFrom-ToolJson {
    # Tools print one indented JSON object on stdout; skip any library chatter before it.
    param([object[]]$Lines)
    $text = @($Lines | ForEach-Object { "$_" })
    $start = [Array]::IndexOf($text, "{")
    if ($start -lt 0) { throw ("No JSON result in tool output:`n" + ($text -join "`n")) }
    return (($text[$start..($text.Count - 1)]) -join "`n") | ConvertFrom-Json
}

if ($VoiceoverScript -and -not $Market) {
    throw "-Market is required when -VoiceoverScript is given."
}
if ($null -eq (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Run scripts\bootstrap-video-editor-workspace.ps1 first."
}

$arguments = @(
    "run", "--project", $workspaceRoot, "tk-ops-workspace", "render", "showcase",
    "--source", (Resolve-Full $Source),
    "--run-dir", (Resolve-Full $RunDir),
    "--output-name", $OutputName
)
if ($SegmentsJson) { $arguments += @("--segments-json", (Resolve-Full $SegmentsJson)) }
if ($Title) { $arguments += @("--title", $Title) }
if ($Cta) { $arguments += @("--cta", $Cta) }
if ($ArrowPath) { $arguments += @("--arrow-path", (Resolve-Full $ArrowPath)) }
if ($CartPath) { $arguments += @("--cart-path", (Resolve-Full $CartPath)) }
if ($FfmpegPath) { $arguments += @("--ffmpeg", (Resolve-Full $FfmpegPath)) }
if ($FfprobePath) { $arguments += @("--ffprobe", (Resolve-Full $FfprobePath)) }
if ($FontFile) { $arguments += @("--fontfile", (Resolve-Full $FontFile)) }
if ($SkipQa) { $arguments += "--skip-qa" }

$renderLines = @(& uv @arguments)
$renderExit = $LASTEXITCODE
if ($renderExit -ne 0) {
    Write-Output ($renderLines -join "`n")
    if ($renderExit -eq 3) { throw "Render finished but delivery QA failed (see qa.errors). Inspect and re-cut; do not deliver." }
    throw "Render failed (exit $renderExit). See the JSON above."
}
$render = ConvertFrom-ToolJson $renderLines

$voiceover = $null
if ($VoiceoverScript) {
    $voArgs = @{
        Video = $render.output; VoiceoverScript = $VoiceoverScript; RunDir = (Resolve-Full $RunDir)
        Market = $Market; Category = $Category; TtsBackend = $TtsBackend; Speed = $Speed
    }
    if ($FfmpegPath) { $voArgs.FfmpegPath = $FfmpegPath }
    if ($FfprobePath) { $voArgs.FfprobePath = $FfprobePath }
    if ($Language) { $voArgs.Language = $Language }
    if ($ApprovedBy) { $voArgs.ApprovedBy = $ApprovedBy }
    if ($Voice) { $voArgs.Voice = $Voice }
    if ($BurnSubtitles) { $voArgs.BurnSubtitles = $true }
    $voiceoverJson = & (Join-Path $PSScriptRoot "add-voiceover-subtitles.ps1") @voArgs
    $voiceover = ConvertFrom-ToolJson @($voiceoverJson)
}

$render | Add-Member -NotePropertyName voiceover -NotePropertyValue $voiceover -Force
$render | ConvertTo-Json -Depth 8
