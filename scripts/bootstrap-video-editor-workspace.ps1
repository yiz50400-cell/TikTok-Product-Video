[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$Confirmed,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Output "Usage: powershell -File scripts/bootstrap-video-editor-workspace.ps1 [-Apply -Confirmed]"
    Write-Output "Without -Apply this command only prints a read-only environment plan."
    exit 0
}

if ($Apply -and -not $Confirmed) {
    throw "Applying environment changes requires -Confirmed after the employee reviews the plan."
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

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($machinePath, $userPath) -join ";"
    if (Test-Path -LiteralPath $bundledBin -PathType Container) {
        $env:Path = "$bundledBin;$env:Path"
    }
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Add-PlanItem {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][System.Collections.Generic.List[object]]$Plan,
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Status,
        [Parameter(Mandatory = $true)][string]$Action,
        [bool]$ChangesState = $false
    )
    $Plan.Add([pscustomobject]@{
        id = $Id
        status = $Status
        action = $Action
        changes_state = $ChangesState
    }) | Out-Null
}

$exampleConfig = Join-Path $workspaceRoot "config\video-editor.example.yaml"
$localConfig = Join-Path $workspaceRoot "config\video-editor.local.yaml"

$hasWinget = Test-LocalCommand "winget"
$hasUv = Test-LocalCommand "uv"
$pythonCommand = Resolve-PythonForVideo
$hasPython = $null -ne $pythonCommand
$hasFfmpeg = (Test-LocalCommand "ffmpeg") -and (Test-NativeCommand { & ffmpeg -version })
$hasFfprobe = (Test-LocalCommand "ffprobe") -and (Test-NativeCommand { & ffprobe -version })
$hasYtDlp = ((Test-LocalCommand "yt-dlp") -and (Test-NativeCommand { & yt-dlp --version })) -or ((Test-LocalCommand "yt-dlp.exe") -and (Test-NativeCommand { & yt-dlp.exe --version }))
$hasLocalConfig = Test-Path -LiteralPath $localConfig -PathType Leaf

$plan = [System.Collections.Generic.List[object]]::new()
Add-PlanItem $plan "winget" ($(if ($hasWinget) { "ready" } else { "missing" })) "Windows official package manager required only when installing missing tools."
Add-PlanItem $plan "uv" ($(if ($hasUv) { "ready" } else { "missing" })) "Install official astral-sh.uv with winget." (-not $hasUv)
Add-PlanItem $plan "python_3_12" ($(if ($hasPython) { "ready" } else { "missing" })) "Install Python 3.12 runtime through uv for video utility scripts." (-not $hasPython)
Add-PlanItem $plan "ffmpeg_toolchain" ($(if ($hasFfmpeg -and $hasFfprobe) { "ready" } else { "missing" })) "Install Gyan.FFmpeg with winget; provides ffmpeg and ffprobe for probing, transcode, render, and freeze checks." (-not ($hasFfmpeg -and $hasFfprobe))
Add-PlanItem $plan "yt_dlp" ($(if ($hasYtDlp) { "ready" } else { "missing" })) "Install yt-dlp with uv tool for accessible public material downloads." (-not $hasYtDlp)
Add-PlanItem $plan "video_editor_config" ($(if ($hasLocalConfig) { "ready" } else { "missing" })) "Create config/video-editor.local.yaml from secret-free example." (-not $hasLocalConfig)

[pscustomobject]@{
    schema_version = 1
    mode = $(if ($Apply) { "apply" } else { "plan" })
    workspace_root = $workspaceRoot
    performed_external_writes = $false
    items = $plan
} | ConvertTo-Json -Depth 5

if (-not $Apply) {
    exit 0
}

if ((-not $hasUv -or -not ($hasFfmpeg -and $hasFfprobe)) -and -not $hasWinget) {
    throw "winget is unavailable. Install uv and FFmpeg manually, then rerun doctor-video-editor-workspace.ps1."
}

if (-not $hasUv) {
    Invoke-Checked "uv installation" { & winget install --id astral-sh.uv --exact --accept-package-agreements --accept-source-agreements }
    Refresh-ProcessPath
}

if (-not $hasPython) {
    if (-not (Test-LocalCommand "uv")) {
        throw "uv is unavailable after installation."
    }
    Invoke-Checked "Python 3.12 installation" { & uv python install 3.12 }
    Refresh-ProcessPath
}

if (-not ($hasFfmpeg -and $hasFfprobe)) {
    Invoke-Checked "FFmpeg toolchain installation" { & winget install --id Gyan.FFmpeg --exact --accept-package-agreements --accept-source-agreements }
    Refresh-ProcessPath
}

if (-not $hasYtDlp) {
    if (-not (Test-LocalCommand "uv")) {
        throw "uv is unavailable; cannot install yt-dlp."
    }
    Invoke-Checked "yt-dlp installation" { & uv tool install yt-dlp }
    Refresh-ProcessPath
}

if (-not $hasLocalConfig) {
    if (-not (Test-Path -LiteralPath $exampleConfig -PathType Leaf)) {
        throw "Missing config/video-editor.example.yaml."
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $localConfig) | Out-Null
    Copy-Item -LiteralPath $exampleConfig -Destination $localConfig
}

& (Join-Path $PSScriptRoot "doctor-video-editor-workspace.ps1")
exit $LASTEXITCODE
