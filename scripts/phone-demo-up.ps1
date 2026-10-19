[CmdletBinding()]
param(
    [switch]$ConfigOnly
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
    if (Test-Path -LiteralPath $envFile -PathType Leaf) { return }
    if (Test-Path -LiteralPath $envFile) { throw 'phone-demo.env exists but is not a regular file; no services were changed.' }
    $secrets = @(1..13 | ForEach-Object { New-UrlSafeSecret })
    # AES-GCM email encryption and the F13 KEK are specified as URL-safe Base64
    # encodings of exactly 32 bytes. Other values only have a minimum entropy length.
    $secrets[9] = New-UrlSafeSecret 32
    $secrets[12] = New-UrlSafeSecret 32
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
        "EXPORT_KEK=$($secrets[12])"
    )
    [System.IO.File]::WriteAllLines($envFile, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host 'Created ignored phone-demo.env with unique local test/demo secrets. Values were not printed.'
}

if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf)) { throw 'phone-demo Compose file is missing; no services were started.' }
Assert-LocalEnvFile
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; no services were started.' }
Set-Location $root
& $docker.Source compose -f $composeFile --env-file $envFile -p $project config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo Compose configuration validation failed.' }
if ($ConfigOnly) { Write-Host 'Phone-demo Compose configuration is valid. No services were started.'; exit 0 }
& $docker.Source compose -f $composeFile --env-file $envFile -p $project up -d --build --wait
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo startup failed. Use the project-scoped compose logs command to inspect it.' }
Write-Host 'Phone demo is ready at http://127.0.0.1:8000/health/live; Mailpit is http://127.0.0.1:8025.'
