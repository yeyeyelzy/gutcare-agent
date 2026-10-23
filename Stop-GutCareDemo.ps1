[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'compose.phone-demo.yaml') -PathType Leaf) {
    $PSScriptRoot
} else {
    Split-Path -Parent $PSScriptRoot
}
$stopScript = Join-Path $root 'scripts\phone-demo-down.ps1'
if (-not (Test-Path -LiteralPath $stopScript -PathType Leaf)) {
    throw 'Package is incomplete: scripts/phone-demo-down.ps1 is missing.'
}
& $stopScript
if ($LASTEXITCODE -ne 0) {
    throw 'Phone-demo stop script failed. No volume purge was requested.'
}
Write-Host 'GutCare demo services stopped. Project data volumes were kept.'
