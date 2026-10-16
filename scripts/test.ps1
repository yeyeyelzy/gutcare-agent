[CmdletBinding()]
param([ValidateSet('unit', 'integration', 'contract')][string]$Suite = 'unit')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
if (-not $uv) { throw 'Project uv resolver did not return an executable.' }
if (-not $node) { throw 'Project Node resolver did not return an executable.' }
Set-Location $root
if (-not (Test-Path -LiteralPath 'backend/pyproject.toml')) { throw 'Backend project file is missing.' }

$pytestArgs = @('run', '--locked', '--python', $python, 'pytest')
if ($Suite -eq 'integration') { $pytestArgs += @('-m', 'integration') }
if ($Suite -eq 'contract') { $pytestArgs += @('-m', 'contract') }
Push-Location 'backend'
try {
    & $uv @pytestArgs
    if ($LASTEXITCODE -ne 0) { throw "pytest $Suite failed." }
} finally { Pop-Location }

$corepack = Join-Path (Split-Path -Parent $node) 'node_modules\corepack\dist\corepack.js'
if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'Project Node 22 Corepack runtime is missing.' }
$env:COREPACK_HOME = Join-Path $root '.runtime\corepack'
Push-Location (Join-Path $root 'app')
try { $pnpmVersion = & $node $corepack pnpm --version } finally { Pop-Location }
if ($LASTEXITCODE -ne 0 -or $pnpmVersion -ne '10.28.0') { throw "Project pnpm 10.28.0 is required; resolver reports '$pnpmVersion'." }
Push-Location (Join-Path $root 'app')
try {
    & $node $corepack pnpm --filter gutcare-mobile... run test
    if ($LASTEXITCODE -ne 0) { throw 'APP test suite failed.' }
} finally { Pop-Location }
