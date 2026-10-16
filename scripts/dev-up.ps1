[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; no services were started.' }
& (Join-Path $PSScriptRoot 'bootstrap.ps1')
if (-not $?) { throw 'Bootstrap failed.' }
Set-Location $root
$composeArgs = @('compose', 'up', '-d', 'postgres', 'redis', 'mailpit', 'minio', 'gateway')
& $docker.Source @composeArgs
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose startup failed.' }
