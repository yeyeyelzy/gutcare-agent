[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $node) { throw 'Project Node resolver did not return an executable.' }
$corepack = Join-Path (Split-Path -Parent $node) 'node_modules\corepack\dist\corepack.js'
if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'Project Node 22 Corepack runtime is missing.' }
$env:COREPACK_HOME = Join-Path $root '.runtime\corepack'
Push-Location (Join-Path $root 'app')
try {
    $version = & $node $corepack pnpm --version
    if ($LASTEXITCODE -ne 0 -or $version -ne '10.28.0') { throw "pnpm 10.28.0 is required; resolver reports '$version'." }
    & $node $corepack pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'APP dependency installation from pnpm-lock.yaml failed.' }
} finally { Pop-Location }
