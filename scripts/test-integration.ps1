[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
$uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
if (-not $uv) { throw 'Project uv resolver did not return an executable.' }
Set-Location $root

$hasExternalDatabase = -not [string]::IsNullOrWhiteSpace($env:GUTCARE_TEST_DATABASE_URL)
$ownsIntegrationStack = $false
$integrationProject = $null
if (-not $hasExternalDatabase) {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        throw 'PostgreSQL 18 integration tests need Docker Desktop running, or GUTCARE_TEST_DATABASE_URL and GUTCARE_TEST_MIGRATOR_DATABASE_URL for a dedicated gutcare_business_test database.'
    }
    function Get-FreeLoopbackPort {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
        try {
            $listener.Start()
            return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
        } finally {
            $listener.Stop()
        }
    }
    $integrationProject = "gutcare-int-$([guid]::NewGuid().ToString('N').Substring(0, 12))"
    $env:GUTCARE_INTEGRATION_PROJECT = $integrationProject
    $env:GUTCARE_TEST_PG18_HOST_PORT = Get-FreeLoopbackPort
    $env:GUTCARE_TEST_MINIO_HOST_PORT = Get-FreeLoopbackPort
    $env:GUTCARE_TEST_CLAMAV_HOST_PORT = Get-FreeLoopbackPort
    & (Join-Path $PSScriptRoot 'prepare-minio-integration.ps1')
    $ownsIntegrationStack = $true
    & $docker.Source compose -f 'compose.integration.yaml' -p $integrationProject up -d --wait
    if ($LASTEXITCODE -ne 0) {
        & $docker.Source compose -f 'compose.integration.yaml' -p $integrationProject down --remove-orphans
        $ownsIntegrationStack = $false
        throw 'Disposable PostgreSQL 18 integration service could not start.'
    }
    $env:GUTCARE_TEST_DATABASE_URL = "postgresql+psycopg://gutcare_app:gutcare-test-app-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_MIGRATOR_DATABASE_URL = "postgresql+psycopg://gutcare_migrator:gutcare-test-migrator-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_WORKER_PASSWORD = 'gutcare-test-worker-only'
    $env:GUTCARE_TEST_WORKER_DATABASE_URL = "postgresql+psycopg://gutcare_worker:gutcare-test-worker-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_ANALYSIS_WORKER_PASSWORD = 'gutcare-test-analysis-worker-only'
    $env:GUTCARE_TEST_ANALYSIS_WORKER_DATABASE_URL = "postgresql+psycopg://gutcare_analysis_worker:gutcare-test-analysis-worker-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_NOTIFICATION_WORKER_PASSWORD = 'gutcare-test-notification-worker-only'
    $env:GUTCARE_TEST_PRIVACY_WORKER_PASSWORD = 'gutcare-test-privacy-worker-only'
    $env:GUTCARE_TEST_PRIVACY_WORKER_DATABASE_URL = "postgresql+psycopg://gutcare_privacy_worker:gutcare-test-privacy-worker-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_NOTIFICATION_WORKER_DATABASE_URL = "postgresql+psycopg://gutcare_notification_worker:gutcare-test-notification-worker-only@127.0.0.1:$($env:GUTCARE_TEST_PG18_HOST_PORT)/gutcare_business_test"
    $env:GUTCARE_TEST_S3_ENDPOINT = "http://127.0.0.1:$($env:GUTCARE_TEST_MINIO_HOST_PORT)"
    $env:GUTCARE_TEST_S3_ACCESS_KEY = 'gutcare_test_storage'
    $env:GUTCARE_TEST_S3_SECRET_KEY = 'gutcare-test-storage-only'
    $env:GUTCARE_TEST_S3_BUCKET = 'gutcare-files-integration'
    $env:GUTCARE_TEST_CLAMAV_HOST = '127.0.0.1'
    $env:GUTCARE_TEST_CLAMAV_PORT = $env:GUTCARE_TEST_CLAMAV_HOST_PORT
}

if ([string]::IsNullOrWhiteSpace($env:GUTCARE_TEST_MIGRATOR_DATABASE_URL)) {
    throw 'Set GUTCARE_TEST_MIGRATOR_DATABASE_URL for the dedicated gutcare_business_test database.'
}

try {
    Push-Location (Join-Path $root 'backend')
    try {
        & $uv run --locked --project . --python $python pytest -m integration -v
        $integrationExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    if ($integrationExitCode -ne 0) { throw 'PostgreSQL 18 integration tests failed.' }

    if ($ownsIntegrationStack) {
        & powershell -NoProfile -ExecutionPolicy Bypass `
            -File (Join-Path $PSScriptRoot 'test-pg18-backup-restore.ps1')
        $backupRestoreExitCode = $LASTEXITCODE
        if ($backupRestoreExitCode -ne 0) { throw 'PostgreSQL 18 backup/restore rehearsal failed.' }
        Write-Output 'PG18 integration and backup/restore gates passed.'
    }
} finally {
    if ($ownsIntegrationStack) {
        & $docker.Source compose -f 'compose.integration.yaml' -p $integrationProject down --remove-orphans
    }
}
