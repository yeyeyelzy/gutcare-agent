[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $node) { throw 'Project Node resolver did not return an executable.' }

$packageManager = (Get-Content -LiteralPath (Join-Path $root 'app\package.json') -Raw | ConvertFrom-Json).packageManager
if ($packageManager -ne 'pnpm@10.28.0') { throw 'APP requires the package manager pinned in app/package.json.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'pnpm-lock.yaml') -PathType Leaf)) { throw 'Workspace pnpm-lock.yaml is missing.' }
if (-not $env:VITE_API_BASE_URL) { throw 'Set VITE_API_BASE_URL before building the APP.' }

$corepack = Join-Path (Split-Path -Parent $node) 'node_modules\corepack\dist\corepack.js'
if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'Project Node 22 Corepack runtime is missing.' }
$env:COREPACK_HOME = Join-Path $root '.runtime\corepack'
$appPath = Join-Path $root 'app'
Push-Location $appPath
try {
    $version = & $node $corepack pnpm --version
    if ($LASTEXITCODE -ne 0 -or $version -ne '10.28.0') { throw "pnpm 10.28.0 is required; resolver reports '$version'." }
    & $node $corepack pnpm run build:android
    if ($LASTEXITCODE -ne 0) { throw 'APP Android build failed.' }
    & $node $corepack pnpm run build:ios
    if ($LASTEXITCODE -ne 0) { throw 'APP iOS build failed.' }
} finally {
    Pop-Location
}
