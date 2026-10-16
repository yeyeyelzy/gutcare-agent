[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
if (-not $uv) { throw 'Project uv resolver did not return an executable.' }
if (-not (Test-Path -LiteralPath 'backend/pyproject.toml' -PathType Leaf)) {
    throw 'Backend project file is missing.'
}
if (-not (Test-Path -LiteralPath 'backend/uv.lock' -PathType Leaf)) {
    throw 'Backend uv.lock is missing.'
}

$backend = Join-Path $root 'backend'
$venvBin = Join-Path $backend '.venv\Scripts'
$ruff = Join-Path $venvBin 'ruff.exe'
$mypy = Join-Path $venvBin 'mypy.exe'
$pytest = Join-Path $venvBin 'pytest.exe'
$alembic = Join-Path $venvBin 'alembic.exe'

Push-Location $backend
try {
    & $uv sync --project . --locked --group dev --python $python --no-progress
    if ($LASTEXITCODE -ne 0) { throw 'Locked backend dependency sync failed.' }

    foreach ($tool in @($ruff, $mypy, $pytest, $alembic)) {
        if (-not (Test-Path -LiteralPath $tool -PathType Leaf)) {
            throw "Backend tool was not installed: $tool"
        }
    }

    & $ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff format check failed.' }

    & $ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Ruff check failed.' }

    & $mypy src
    if ($LASTEXITCODE -ne 0) { throw 'mypy failed.' }

    $offlineOutput = & $alembic -c (Join-Path $backend 'alembic.ini') upgrade head --sql 2>&1
    $offlineExitCode = $LASTEXITCODE
    if ($offlineExitCode -ne 0) {
        Write-Host "Alembic offline migration compilation failed (exit $offlineExitCode) from ${backend}:" -ForegroundColor Red
        $offlineOutput | ForEach-Object { Write-Host $_ }
        throw 'Alembic offline migration compilation failed.'
    }

    & $pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }
} finally {
    Pop-Location
}

Write-Host 'Backend dependency sync and all backend verification gates passed.' -ForegroundColor Green
