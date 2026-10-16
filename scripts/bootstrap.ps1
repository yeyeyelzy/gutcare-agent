[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; Compose configuration was not validated and no services were started.' }
$composeVersion = & $docker.Source compose version
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose v2 is required.' }

if (-not (Test-Path -LiteralPath '.env' -PathType Leaf)) { throw 'Create a local .env with unique credentials; bootstrap never copies placeholder credentials.' }
$values = @{}
foreach ($line in Get-Content -LiteralPath '.env') {
    if ($line -match '^\s*(?:#.*)?$') { continue }
    if ($line -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') { throw 'Invalid .env syntax; use simple KEY=value entries without quotes.' }
    if ($values.ContainsKey($Matches[1])) { throw "Duplicate .env key: $($Matches[1])" }
    $values[$Matches[1]] = $Matches[2]
}

foreach ($key in @('POSTGRES_BOOTSTRAP_PASSWORD', 'GUTCARE_MIGRATOR_PASSWORD', 'GUTCARE_APP_PASSWORD', 'GUTCARE_WORKER_PASSWORD', 'GUTCARE_ANALYSIS_WORKER_PASSWORD', 'GUTCARE_NOTIFICATION_WORKER_PASSWORD', 'GUTCARE_PRIVACY_WORKER_PASSWORD', 'REDIS_PASSWORD', 'MINIO_ROOT_PASSWORD')) {
    $value = [string]$values[$key]
    if ($value.Length -lt 20 -or $value -notmatch '^[A-Za-z0-9_-]+$' -or $value -match 'CHANGE_ME|replace-with') {
        throw "$key must be replaced with a unique local-only value of at least 20 URL-safe characters. No credential value is printed."
    }
}
$credentialValues = @($values.POSTGRES_BOOTSTRAP_PASSWORD, $values.GUTCARE_MIGRATOR_PASSWORD, $values.GUTCARE_APP_PASSWORD, $values.GUTCARE_WORKER_PASSWORD, $values.GUTCARE_ANALYSIS_WORKER_PASSWORD, $values.GUTCARE_NOTIFICATION_WORKER_PASSWORD, $values.GUTCARE_PRIVACY_WORKER_PASSWORD, $values.REDIS_PASSWORD, $values.MINIO_ROOT_PASSWORD)
if (($credentialValues | Select-Object -Unique).Count -ne 8) {
    throw 'Bootstrap, migrator, app, file-worker, analysis-worker, notification-worker, privacy-worker, Redis, and MinIO credentials must all be different.'
}
if ([string]$values.MINIO_ROOT_USER -notmatch '^[A-Za-z0-9_-]{3,32}$') { throw 'MINIO_ROOT_USER must contain 3–32 URL-safe characters.' }
if ([string]$values.POSTGRES_DB -notmatch '^[a-z][a-z0-9_]{0,62}$' -or [string]$values.POSTGRES_BOOTSTRAP_USER -ne 'gutcare_bootstrap') {
    throw 'POSTGRES_DB must be a lowercase PostgreSQL identifier and POSTGRES_BOOTSTRAP_USER must be gutcare_bootstrap.'
}
if ([string]$values.MINIO_SOURCE_COMMIT -notmatch '^[0-9a-f]{40}$') { throw 'MINIO_SOURCE_COMMIT must be a reviewed full 40-character lowercase commit.' }
if ([string]$values.MINIO_IMAGE_DIGEST -notmatch '^sha256:[0-9a-f]{64}$') { throw 'MINIO_IMAGE_DIGEST must contain the locally inspected image ID in sha256 format.' }
foreach ($key in @('POSTGRES_DB', 'POSTGRES_BOOTSTRAP_USER', 'POSTGRES_BOOTSTRAP_PASSWORD', 'GUTCARE_MIGRATOR_PASSWORD', 'GUTCARE_APP_PASSWORD', 'GUTCARE_WORKER_PASSWORD', 'GUTCARE_ANALYSIS_WORKER_PASSWORD', 'GUTCARE_NOTIFICATION_WORKER_PASSWORD', 'GUTCARE_PRIVACY_WORKER_PASSWORD', 'REDIS_PASSWORD', 'MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD', 'MINIO_SOURCE_COMMIT', 'MINIO_IMAGE_DIGEST', 'MAILPIT_SMTP_PORT', 'MAILPIT_UI_PORT', 'GATEWAY_HTTP_PORT')) {
    $processValue = [Environment]::GetEnvironmentVariable($key)
    if ($null -ne $processValue -and $processValue -cne [string]$values[$key]) {
        throw "Process environment overrides $key from .env; remove the override before starting Compose. Values are not printed."
    }
}

$image = "gutcare-minio:source-$($values.MINIO_SOURCE_COMMIT)"
$imageId = & $docker.Source image inspect $image --format '{{.Id}}' 2>$null
if ($LASTEXITCODE -ne 0 -or [string]$imageId -ne [string]$values.MINIO_IMAGE_DIGEST) {
    throw "The local image $image is missing or its image ID differs from MINIO_IMAGE_DIGEST. Build and independently review the pinned source image first."
}

$composeConfig = & $docker.Source compose config --quiet 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose configuration validation failed.' }
Write-Host 'Bootstrap checks passed. No image was pulled, built, or started.'
