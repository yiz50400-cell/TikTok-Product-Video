[CmdletBinding()]
param(
    [string]$Config,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$env:PYTHONUTF8 = "1"

if ($Help) {
    Write-Output "Usage: powershell -File scripts/doctor-video-editor-workspace.ps1 [-Config <local-config-path>]"
    Write-Output "Read-only check for the standalone TikTok product video editor workspace."
    exit 0
}

function Test-LocalCommand {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$bundledBin = Join-Path $workspaceRoot ".tools\bin"
if (Test-Path -LiteralPath $bundledBin -PathType Container) {
    $env:Path = "$bundledBin;$env:Path"
}

function Test-NativeCommand {
    param([Parameter(Mandatory = $true)][scriptblock]$Command)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command 2>&1 | Out-Null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Resolve-PythonForVideo {
    if ((Test-LocalCommand "python") -and (Test-NativeCommand { & python --version })) {
        return "python"
    }
    if ((Test-LocalCommand "py") -and (Test-NativeCommand { & py --version })) {
        return "py"
    }
    if (Test-LocalCommand "uv") {
        try {
            $candidate = (& uv python find 3.12 2>$null | Select-Object -First 1)
            if ($candidate) {
                $candidate = $candidate.Trim()
                if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-NativeCommand { & $candidate --version })) {
                    return $candidate
                }
            }
        } catch {
            return $null
        }
    }
    return $null
}

$configPath = if ($Config) {
    $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Config)
} else {
    Join-Path $workspaceRoot "config\video-editor.local.yaml"
}

$hasWinget = Test-LocalCommand "winget"
$hasUv = Test-LocalCommand "uv"
$hasFfmpeg = Test-LocalCommand "ffmpeg"
$hasFfprobe = Test-LocalCommand "ffprobe"
$hasYtDlp = (Test-LocalCommand "yt-dlp") -or (Test-LocalCommand "yt-dlp.exe")
$hasConfig = Test-Path -LiteralPath $configPath -PathType Leaf

$pythonCommand = Resolve-PythonForVideo
$pythonRunnable = $null -ne $pythonCommand

$ffmpegRunnable = $hasFfmpeg -and (Test-NativeCommand { & ffmpeg -version })
$ffprobeRunnable = $hasFfprobe -and (Test-NativeCommand { & ffprobe -version })
$ytDlpRunnable = $hasYtDlp -and (Test-NativeCommand { & yt-dlp --version })

$failureCodes = [System.Collections.Generic.List[string]]::new()
if (-not $hasWinget) { $failureCodes.Add("winget_missing") }
if (-not $hasUv) { $failureCodes.Add("uv_missing") }
if (-not $pythonRunnable) { $failureCodes.Add("python_missing") }
if (-not $ffmpegRunnable) { $failureCodes.Add("ffmpeg_missing") }
if (-not $ffprobeRunnable) { $failureCodes.Add("ffprobe_missing") }
if (-not $ytDlpRunnable) { $failureCodes.Add("yt_dlp_missing") }
if (-not $hasConfig) { $failureCodes.Add("video_editor_config_missing") }

[pscustomobject]@{
    schema_version = 1
    workspace_root = $workspaceRoot
    config_path = $configPath
    video_editor_environment = [pscustomobject]@{
        winget_available = $hasWinget
        uv_available = $hasUv
        python_available = $pythonRunnable
        python_path = $pythonCommand
        ffmpeg_available = $ffmpegRunnable
        ffprobe_available = $ffprobeRunnable
        yt_dlp_available = $ytDlpRunnable
        config_exists = $hasConfig
        failure_codes = @($failureCodes)
    }
    host_checks_still_required = @(
        "current_codex_loads_tiktok_product_video_editor_skill",
        "employee_material_can_be_probed",
        "employee_material_can_render_h264_mp4_after_script_approval"
    )
    performed_external_writes = $false
} | ConvertTo-Json -Depth 6

if ($failureCodes.Count -gt 0) {
    exit 1
}
exit 0
