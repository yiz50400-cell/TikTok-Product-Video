[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [string]$FfprobePath = "",
    # Require an AAC audio stream (use for voiced deliveries such as *.voiced.mp4).
    [switch]$RequireAudio
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$videoPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Video)
if (-not (Test-Path -LiteralPath $videoPath -PathType Leaf)) {
    throw "Video does not exist: $videoPath"
}

if ($FfprobePath) {
    $probe = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($FfprobePath)
} else {
    $command = Get-Command ffprobe -ErrorAction SilentlyContinue
    if ($null -eq $command) { throw "ffprobe is required for delivery verification." }
    $probe = $command.Source
}

$json = & $probe "-v" "error" "-show_entries" "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate,channels,sample_rate" "-of" "json" $videoPath | ConvertFrom-Json
if ($LASTEXITCODE -ne 0) { throw "ffprobe failed with exit code $LASTEXITCODE." }
$stream = @($json.streams | Where-Object { $_.codec_name -eq "h264" } | Select-Object -First 1)
$audio = @($json.streams | Where-Object { $_.codec_type -eq "audio" } | Select-Object -First 1)
$duration = [double]$json.format.duration
$errors = New-Object System.Collections.Generic.List[string]
if ($stream.Count -eq 0) { $errors.Add("missing_h264_video_stream") }
if ($stream.Count -gt 0 -and ($stream[0].width -ne 1080 -or $stream[0].height -ne 1920)) { $errors.Add("expected_1080x1920") }
if ($stream.Count -gt 0 -and $stream[0].pix_fmt -ne "yuv420p") { $errors.Add("expected_yuv420p") }
if ($duration -le 0) { $errors.Add("invalid_duration") }
if ($RequireAudio -and $audio.Count -eq 0) { $errors.Add("missing_audio_stream") }
if ($RequireAudio -and $audio.Count -gt 0 -and $audio[0].codec_name -ne "aac") { $errors.Add("expected_aac_audio") }

[pscustomobject]@{
    video = $videoPath
    duration_seconds = $duration
    h264 = ($stream.Count -gt 0)
    width = if ($stream.Count -gt 0) { $stream[0].width } else { $null }
    height = if ($stream.Count -gt 0) { $stream[0].height } else { $null }
    pix_fmt = if ($stream.Count -gt 0) { $stream[0].pix_fmt } else { $null }
    audio = ($audio.Count -gt 0)
    audio_codec = if ($audio.Count -gt 0) { $audio[0].codec_name } else { $null }
    errors = @($errors)
    passed = ($errors.Count -eq 0)
} | ConvertTo-Json -Depth 4

if ($errors.Count -gt 0) { exit 1 }
