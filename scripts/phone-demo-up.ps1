[CmdletBinding()]
param(
    [switch]$ConfigOnly,
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
$project = 'gutcare-phone-demo'

function New-UrlSafeSecret([int]$Bytes = 48) {
    $buffer = [byte[]]::new($Bytes)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Assert-LocalEnvFile {
    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        $lines = @(Get-Content -LiteralPath $envFile)
        $present = @{}
        $usedValues = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
        foreach ($line in $lines) {
            if ($line -match '^([A-Z0-9_]+)=(.*)$') {
                $present[$Matches[1]] = $Matches[2]
                [void]$usedValues.Add($Matches[2])
            }
        }
        if ($present.ContainsKey('AGENT_SERVICE_TOKEN') -and $present.ContainsKey('AGENT_INTERNAL_TOKEN') -and
            $present['AGENT_SERVICE_TOKEN'] -and $present['AGENT_SERVICE_TOKEN'] -ceq $present['AGENT_INTERNAL_TOKEN']) {
            throw 'AGENT_SERVICE_TOKEN and AGENT_INTERNAL_TOKEN must be distinct; no services were started.'
        }
        $additions = [System.Collections.Generic.List[string]]::new()
        foreach ($key in @('MINIO_ROOT_PASSWORD', 'MINIO_APP_ACCESS_KEY', 'MINIO_APP_SECRET_KEY', 'FILES_CAPABILITY_SECRET', 'AGENT_SERVICE_TOKEN', 'AGENT_INTERNAL_TOKEN')) {
            if (-not $present.ContainsKey($key) -or [string]::IsNullOrWhiteSpace([string]$present[$key])) {
                $secretBytes = if ($key -eq 'MINIO_APP_SECRET_KEY') { 30 } elseif ($key -eq 'MINIO_APP_ACCESS_KEY') { 15 } else { 48 }
                do { $secret = New-UrlSafeSecret $secretBytes } while (-not $usedValues.Add($secret))
                $additions.Add("${key}=$secret")
            }
        }
        if ($additions.Count -gt 0) {
            [System.IO.File]::AppendAllLines($envFile, $additions, [System.Text.UTF8Encoding]::new($false))
            Write-Host 'Added missing isolated demo secrets to phone-demo.env. Values were not printed.'
        }
        return
    }
    if (Test-Path -LiteralPath $envFile) { throw 'phone-demo.env exists but is not a regular file; no services were changed.' }
    $secrets = @(1..19 | ForEach-Object { New-UrlSafeSecret })
    # AES-GCM email encryption and the F13 KEK are specified as URL-safe Base64
    # encodings of exactly 32 bytes. Other values only have a minimum entropy length.
    $secrets[9] = New-UrlSafeSecret 32
    $secrets[12] = New-UrlSafeSecret 32
    $secrets[15] = New-UrlSafeSecret 15
    $secrets[16] = New-UrlSafeSecret 30
    if (($secrets | Select-Object -Unique).Count -ne $secrets.Count) { throw 'Random secret generation collision; retry without printing values.' }
    $content = @(
        '# Generated locally for the isolated phone demo. Never commit or reuse in production.',
        "POSTGRES_BOOTSTRAP_PASSWORD=$($secrets[0])",
        "GUTCARE_MIGRATOR_PASSWORD=$($secrets[1])",
        "GUTCARE_APP_PASSWORD=$($secrets[2])",
        "GUTCARE_WORKER_PASSWORD=$($secrets[3])",
        "GUTCARE_ANALYSIS_WORKER_PASSWORD=$($secrets[4])",
        "GUTCARE_NOTIFICATION_WORKER_PASSWORD=$($secrets[5])",
        "GUTCARE_PRIVACY_WORKER_PASSWORD=$($secrets[6])",
        "REDIS_PASSWORD=$($secrets[7])",
        "AUTH_EMAIL_LOOKUP_PEPPER=$($secrets[8])",
        "AUTH_EMAIL_ENCRYPTION_KEY=$($secrets[9])",
        "AUTH_JWT_SIGNING_KEY=$($secrets[10])",
        "MOOD_IDEMPOTENCY_HMAC_KEY=$($secrets[11])",
        "EXPORT_KEK=$($secrets[12])",
        "MINIO_ROOT_PASSWORD=$($secrets[13])",
        "FILES_CAPABILITY_SECRET=$($secrets[14])",
        "MINIO_APP_ACCESS_KEY=$($secrets[15])",
        "MINIO_APP_SECRET_KEY=$($secrets[16])",
        "AGENT_SERVICE_TOKEN=$($secrets[17])",
        "AGENT_INTERNAL_TOKEN=$($secrets[18])"
    )
    [System.IO.File]::WriteAllLines($envFile, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Created ignored phone-demo.env with unique local test/demo secrets. Values were not printed.'
}

if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) { throw 'phone-demo Compose file is missing; no services were started.' }
Assert-LocalEnvFile
$minioContext = Join-Path $root '.downloads\minio-context'
$minioInitContext = Join-Path $root '.downloads\phone-demo-minio-init-context'
if (-not (Test-Path -LiteralPath (Join-Path $minioContext 'Dockerfile') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioContext 'minio') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioContext 'mc') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioInitContext 'Dockerfile') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioInitContext 'mc') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioInitContext 'phone-demo-minio-init.py') -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $minioInitContext 'phone-demo-app-policy.json') -PathType Leaf)) {
    & (Join-Path $PSScriptRoot 'prepare-minio-integration.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned MinIO test runtime preparation failed.' }
}
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; no services were started.' }
Set-Location $root
& $docker.Source compose -f $composeFile --env-file $envFile -p $project config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo Compose configuration validation failed.' }
if ($ConfigOnly) { Write-Host 'Phone-demo Compose configuration is valid. No services were started.'; exit 0 }
$upArgs = @('compose', '-f', $composeFile, '--env-file', $envFile, '-p', $project, 'up', '-d')
if ($NoBuild) { $upArgs += '--no-build' } else { $upArgs += '--build' }
$upArgs += '--wait'
& $docker.Source @upArgs
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo startup failed. Use the project-scoped compose logs command to inspect it.' }
Write-Host 'Phone demo is ready at http://127.0.0.1:8000/health/live; Mailpit is http://127.0.0.1:8025. Private MinIO and ClamAV are healthy.'
