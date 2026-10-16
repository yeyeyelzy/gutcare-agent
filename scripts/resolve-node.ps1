[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not [string]::IsNullOrWhiteSpace($env:GUTCARE_NODE)) {
    $candidate = $env:GUTCARE_NODE
} else {
    $candidate = Join-Path $projectRoot '.runtime\node-v22.23.3\node.exe'
}

if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
    throw "Node executable not found: $candidate"
}

$resolved = (Resolve-Path -LiteralPath $candidate).Path
$versionText = & $resolved --version
if ($LASTEXITCODE -ne 0) { throw "Unable to query Node version: $resolved" }
if ($versionText -notmatch '^v22\.') { throw "Node 22.x is required; '$resolved' reports '$versionText'." }

$resolved
