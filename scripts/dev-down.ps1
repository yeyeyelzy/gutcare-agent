[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; no services were changed.' }
Set-Location $root
& $docker.Source compose down
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose shutdown failed.' }
