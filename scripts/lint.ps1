[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
if (-not $uv) { throw 'Project uv resolver did not return an executable.' }
Set-Location $root
& (Join-Path $PSScriptRoot 'validate-consent-notices.ps1')
if (-not $?) { throw 'Consent notice artifact validation failed.' }

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
