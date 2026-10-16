[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
if (-not $uv) { throw 'Project uv resolver did not return an executable.' }
if (-not $node) { throw 'Project Node resolver did not return an executable.' }
Set-Location $root

$corepack = Join-Path (Split-Path -Parent $node) 'node_modules\corepack\dist\corepack.js'
if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'Project Node 22 Corepack runtime is missing.' }
$env:COREPACK_HOME = Join-Path $root '.runtime\corepack'
Push-Location (Join-Path $root 'app')
try { $pnpmVersion = & $node $corepack pnpm --version } finally { Pop-Location }
if ($LASTEXITCODE -ne 0 -or $pnpmVersion -ne '10.28.0') { throw "Project pnpm 10.28.0 is required; resolver reports '$pnpmVersion'." }

if (-not (Test-Path -LiteralPath 'pnpm-lock.yaml' -PathType Leaf)) { throw 'Workspace pnpm-lock.yaml is missing.' }
Push-Location (Join-Path $root 'app')
try {
    & $node $corepack pnpm --filter gutcare-mobile... run typecheck
    if ($LASTEXITCODE -ne 0) { throw 'APP typecheck failed.' }
} finally { Pop-Location }

if (-not (Test-Path -LiteralPath 'backend/pyproject.toml') -or -not (Test-Path -LiteralPath 'backend/uv.lock')) { throw 'Backend project or uv.lock is missing.' }
Push-Location 'backend'
try {
    & $uv run --locked --python $python ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }
    & $uv run --locked --python $python ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff check failed.' }
    & $uv run --locked --python $python mypy src
    if ($LASTEXITCODE -ne 0) { throw 'mypy failed.' }
} finally { Pop-Location }
