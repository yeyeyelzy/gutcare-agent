[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$cacheDirectory = Join-Path $projectRoot '.runtime\uv-cache'

if (-not (Test-Path -LiteralPath $cacheDirectory -PathType Container)) {
    New-Item -ItemType Directory -Path $cacheDirectory -Force | Out-Null
}
$env:UV_CACHE_DIR = (Resolve-Path -LiteralPath $cacheDirectory).Path

if (-not [string]::IsNullOrWhiteSpace($env:GUTCARE_UV)) {
    $candidate = $env:GUTCARE_UV
} else {
    $candidate = Join-Path $projectRoot '.runtime\uv-0.13.1\uv.exe'
}

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    throw "uv executable not found: $candidate"
}

$resolved = (Resolve-Path -LiteralPath $candidate).Path
$versionText = & $resolved --version
if ($LASTEXITCODE -ne 0) { throw "Unable to query uv version: $resolved" }
if ($versionText -notmatch '^uv 0\.13\.1(?:\s|$)') { throw "uv 0.13.1 is required; '$resolved' reports '$versionText'." }

# Emit one success-stream object so PowerShell callers can capture exactly the path.
$resolved
