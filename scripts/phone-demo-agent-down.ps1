[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf) -or -not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Phone-demo files are missing; no Docker services were changed.'
}
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Docker CLI is unavailable; no services were changed.' }
Set-Location $root
& $docker.Source compose --profile agent -f $composeFile --env-file $envFile -p gutcare-phone-demo stop analysis-dispatcher agent
if ($LASTEXITCODE -ne 0) { throw 'F08 mock Agent profile did not stop cleanly.' }
Write-Host 'F08 mock Agent and dispatcher stopped; all phone-demo data volumes were kept.'
