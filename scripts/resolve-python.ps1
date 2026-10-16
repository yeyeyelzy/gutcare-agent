[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not [string]::IsNullOrWhiteSpace($env:GUTCARE_PYTHON)) {
    $candidate = $env:GUTCARE_PYTHON
} else {
    $candidate = Join-Path $projectRoot '.runtime\cpython-3.13.16\python.exe'
}

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    throw "Python executable not found: $candidate"
}

$resolved = (Resolve-Path -LiteralPath $candidate).Path
# Keep the Python string literal single-quoted: Windows PowerShell's native
# argument marshalling otherwise strips embedded double quotes before Python
# receives the -c source.
$versionText = & $resolved -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to query Python version: $resolved"
}
if ($versionText -notmatch '^3\.13\.') {
    throw "Python 3.13 is required; '$resolved' reports '$versionText'."
}

# Emit one success-stream object so PowerShell callers can capture the path.
$resolved
