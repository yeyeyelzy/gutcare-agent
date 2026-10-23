[CmdletBinding()]
param([ValidateSet('agent', 'analysis-dispatcher', 'record-image-dispatcher', 'medical-parse-dispatcher')][string]$Service = 'analysis-dispatcher', [switch]$Follow)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf) -or -not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Phone-demo files are missing; no Docker resources were changed.'
}
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Docker CLI is unavailable.' }
Set-Location $root
$args = @('compose', '--profile', 'agent', '-f', $composeFile, '--env-file', $envFile, '-p', 'gutcare-competition-demo', 'logs', '--tail', '100')
if ($Follow) { $args += '--follow' }
$args += $Service
& $docker.Source @args
if ($LASTEXITCODE -ne 0) { throw 'Unable to read the selected phone-demo service logs.' }
