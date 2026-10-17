[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$root = Split-Path -Parent $PSScriptRoot
$runId = [guid]::NewGuid().ToString('N').Substring(0, 12)
$project = "gutcare-auth-e2e-$runId"
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Docker CLI is required for the isolated authentication E2E.' }
$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd([char[]]@(
    [System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar
))
$runWorkDir = [System.IO.Path]::GetFullPath((Join-Path $tempRoot "gutcare-auth-e2e-$runId-work"))
if ([System.IO.Path]::GetDirectoryName($runWorkDir) -ne $tempRoot -or
    [System.IO.Path]::GetFileName($runWorkDir) -ne "gutcare-auth-e2e-$runId-work" -or
    (Test-Path -LiteralPath $runWorkDir)) {
    throw 'Temporary E2E working directory is not an unused exact child of the system temp directory.'
}
function Get-FreeLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    try { $listener.Start(); return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port }
    finally { $listener.Stop() }
}

function New-EphemeralSecret {
    $bytes = [byte[]]::new(48)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Get-PropertyValue([object]$Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties | Where-Object { $_.Name -ieq $Name } | Select-Object -First 1
    if ($property) { return $property.Value }
    return $null
}

function Invoke-Http([string]$BaseUrl, [string]$Path, [string]$Method = 'GET', [object]$Body = $null, [string]$Bearer = $null) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), "$BaseUrl$Path")
    $request.Headers.Accept.ParseAdd('application/json')
    $request.Headers.Accept.ParseAdd('application/problem+json')
    $request.Headers.Add('X-Request-ID', [guid]::NewGuid().ToString())
    $request.Headers.Add('X-App-Version', 'b01-4-auth-e2e')
    if ($Path -eq '/__test/shutdown' -and $script:bridgeStopToken) { $request.Headers.Add('X-Test-Stop', $script:bridgeStopToken) }
    if ($Bearer) { $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Bearer) }
    if ($null -ne $Body) {
        $json = ConvertTo-Json -InputObject $Body -Depth 12 -Compress
        $request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, 'application/json')
    }
    $response = $script:httpClient.SendAsync($request).GetAwaiter().GetResult()
    try {
        $text = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsed = $null
        if ($text) { try { $parsed = ConvertFrom-Json -InputObject $text } catch { $parsed = $text } }
        return [pscustomobject]@{
            Status = [int]$response.StatusCode
            Body = $parsed
            ContentType = [string]$response.Content.Headers.ContentType.MediaType
        }
    } finally {
        $response.Dispose()
        $request.Dispose()
    }
}

function Assert-Status([object]$Response, [int]$Expected, [string]$Stage) {
    if ($Response.Status -ne $Expected) {
        $safeDetails = @()
        if ($Response.Status -eq 422) {
            foreach ($issue in @(Get-PropertyValue $Response.Body 'errors')) {
                $location = @(Get-PropertyValue $issue 'location') -join '.'
                $kind = [string](Get-PropertyValue $issue 'code')
                if ($location -or $kind) { $safeDetails += "${location}:$kind" }
            }
        }
        $bodyKeys = @($Response.Body.PSObject.Properties.Name) -join ','
        $detailText = if ($safeDetails.Count -gt 0) { ' fields=' + ($safeDetails -join ',') } else { " response_keys=$bodyKeys" }
        throw "$Stage failed: expected HTTP $Expected, received $($Response.Status).$detailText Response body suppressed."
    }
    Write-Host "$Stage HTTP $($Response.Status)"
}

function Get-MailToken([string]$MailpitUrl, [string]$Recipient, [string]$Subject) {
    $deadline = (Get-Date).AddSeconds(25)
    while ((Get-Date) -lt $deadline) {
        $listing = Invoke-Http $MailpitUrl '/api/v1/messages?limit=50'
        if ($listing.Status -ne 200) { throw 'Mailpit message listing failed; response body suppressed.' }
        $items = Get-PropertyValue $listing.Body 'messages'
        if (-not $items) { $items = Get-PropertyValue $listing.Body 'Messages' }
        foreach ($item in @($items)) {
            $to = Get-PropertyValue $item 'To'
            $toText = ConvertTo-Json -InputObject $to -Depth 8 -Compress
            $mailSubject = [string](Get-PropertyValue $item 'Subject')
            if ($toText -notmatch [regex]::Escape($Recipient) -or $mailSubject -ne $Subject) { continue }
            $messageId = [string](Get-PropertyValue $item 'ID')
            if (-not $messageId) { $messageId = [string](Get-PropertyValue $item 'Id') }
            if (-not $messageId) { continue }
            $detail = Invoke-Http $MailpitUrl ("/api/v1/message/{0}" -f [uri]::EscapeDataString($messageId))
            if ($detail.Status -ne 200) { continue }
            $text = [string](Get-PropertyValue $detail.Body 'Text')
            if (-not $text) { $text = [string](Get-PropertyValue (Get-PropertyValue $detail.Body 'Message') 'Text') }
            $match = [regex]::Match($text, '(?m)^\s*([A-Za-z0-9_-]{60,})\s*$')
            if ($match.Success) { return $match.Groups[1].Value }
        }
        Start-Sleep -Milliseconds 300
    }
    throw "Mailpit did not provide the expected synthetic $Subject message. Body suppressed."
}

function Assert-Problem([object]$Response, [int]$Status, [string]$Stage) {
    if ($Response.Status -ne $Status -or $Response.ContentType -ne 'application/problem+json') {
        throw "$Stage did not return the expected RFC 9457 status/content type. Response body suppressed."
    }
    Write-Host "$Stage HTTP $($Response.Status) problem+json"
}

function Get-SafeStartupDiagnostic {
    $content = @()
    foreach ($path in @($stdoutPath, $stderrPath)) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { $content += Get-Content -LiteralPath $path -ErrorAction SilentlyContinue }
    }
    $safe = $content -join "`n"
    foreach ($secret in @($authPassword, $newPassword, $bootstrapPassword, $migratorPassword, $appPassword, $workerPassword, $analysisPassword, $notificationPassword, $privacyPassword, $redisPassword, $pepper, $jwtKey, $emailEncryptionKey, $script:bridgeStopToken)) {
        if ($secret) { $safe = $safe.Replace($secret, '[redacted]') }
    }
    $safe = [regex]::Replace($safe, '(?i)(postgres(?:ql)?(?:\+psycopg)?|redis)://[^@\s]+@', '$1://[redacted]@')
    $safe = [regex]::Replace($safe, '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[synthetic-email]')
    $safe = [regex]::Replace($safe, '(?i)(password|token|secret|key)\s*[:=]\s*[^\s,;]+', '$1=[redacted]')
    $safe = [regex]::Replace($safe, '[A-Za-z]:\\[^\r\n:" ]+', '[path]')
    $lines = @($safe -split "`r?`n" | Where-Object { $_ -match '(?i)error|exception|traceback|failed|invalid|no such|not found' } | Select-Object -Last 3)
    if ($lines.Count -eq 0) {
        $sizes = @($stdoutPath, $stderrPath | ForEach-Object { if (Test-Path -LiteralPath $_) { (Get-Item -LiteralPath $_).Length } else { 0 } })
        return "no classified diagnostic (stdout_bytes=$($sizes[0]), stderr_bytes=$($sizes[1]))"
    }
    return (($lines -join ' ') -replace '\s+', ' ').Substring(0, [Math]::Min(400, (($lines -join ' ') -replace '\s+', ' ').Length))
}

function Get-SafeCapturedDiagnostic([object[]]$Items) {
    $safe = $Items -join "`n"
    foreach ($secret in @($authPassword, $newPassword, $bootstrapPassword, $migratorPassword, $appPassword, $workerPassword, $analysisPassword, $notificationPassword, $privacyPassword, $redisPassword, $pepper, $jwtKey, $emailEncryptionKey, $script:bridgeStopToken)) {
        if ($secret) { $safe = $safe.Replace($secret, '[redacted]') }
    }
    $safe = [regex]::Replace($safe, '(?i)(postgres(?:ql)?(?:\+psycopg)?|redis)://[^@\s]+@', '$1://[redacted]@')
    $safe = [regex]::Replace($safe, '\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[synthetic-email]')
    $safe = [regex]::Replace($safe, '(?i)(password|token|secret|key)\s*[:=]\s*[^\s,;]+', '$1=[redacted]')
    $safe = [regex]::Replace($safe, '[A-Za-z]:\\[^\r\n:" ]+', '[path]')
    $lines = @($safe -split "`r?`n" | Where-Object { $_ -match '(?i)error|exception|traceback|failed|invalid|no such|not found|unable' } | Select-Object -Last 3)
    if ($lines.Count -eq 0) { return 'unclassified diagnostic; details suppressed' }
    $text = ($lines -join ' ') -replace '\s+', ' '
    return $text.Substring(0, [Math]::Min(350, $text.Length))
}

$ports = @{}
foreach ($name in @('pg', 'redis', 'smtp', 'mailpit', 'api')) {
    $port = Get-FreeLoopbackPort
    if ($ports.Values -contains $port) { throw 'Port allocator returned a duplicate port; nothing was started.' }
    $ports[$name] = $port
}
foreach ($entry in $ports.GetEnumerator()) {
    $probe = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $probe.ConnectAsync('127.0.0.1', [int]$entry.Value)
        if ($task.Wait(250) -and $probe.Connected) { throw "Selected local port for $($entry.Key) is occupied; no unknown process will be stopped." }
    } catch [System.Net.Sockets.SocketException] { }
    finally { $probe.Dispose() }
}

$authPassword = New-EphemeralSecret
$newPassword = New-EphemeralSecret
$bootstrapPassword = New-EphemeralSecret
$migratorPassword = New-EphemeralSecret
$appPassword = New-EphemeralSecret
$workerPassword = New-EphemeralSecret
$analysisPassword = New-EphemeralSecret
$notificationPassword = New-EphemeralSecret
$privacyPassword = New-EphemeralSecret
$redisPassword = New-EphemeralSecret
$script:bridgeStopToken = New-EphemeralSecret
$pepper = New-EphemeralSecret
$jwtKey = New-EphemeralSecret
$emailKeyBytes = [byte[]]::new(32)
$generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try { $generator.GetBytes($emailKeyBytes) } finally { $generator.Dispose() }
$emailEncryptionKey = [Convert]::ToBase64String($emailKeyBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$identity = [guid]::NewGuid().ToString('N')
$emailA = "b01-4-$identity-a@example.com"
$emailB = "b01-4-$identity-b@example.com"
$unknownEmail = "b01-4-$identity-unknown@example.com"
$noticesPath = Join-Path $root 'contracts\consent\registration-notices.json'
$notices = [System.IO.File]::ReadAllText($noticesPath, [System.Text.UTF8Encoding]::new($false)) | ConvertFrom-Json
if ($notices.artifact_classification -ne 'development_test_only' -or $notices.legal_approval_status -ne 'not_approved_for_production') {
    throw 'Refusing E2E: expected repository development/test-only notices; no patient-facing run is allowed.'
}
$privacyNotice = $notices.notices | Where-Object consent_type -eq 'privacy_policy' | Select-Object -First 1
$healthNotice = $notices.notices | Where-Object consent_type -eq 'health_data_processing' | Select-Object -First 1
if (-not $privacyNotice -or -not $healthNotice) { throw 'Registration notice artifact is incomplete.' }

$envNames = @(
    'GUTCARE_TEST_PG18_HOST_PORT', 'GUTCARE_E2E_REDIS_HOST_PORT', 'GUTCARE_E2E_MAILPIT_SMTP_HOST_PORT',
    'GUTCARE_E2E_MAILPIT_API_HOST_PORT', 'GUTCARE_TEST_BOOTSTRAP_PASSWORD', 'GUTCARE_TEST_MIGRATOR_PASSWORD',
    'GUTCARE_TEST_APP_PASSWORD', 'GUTCARE_TEST_WORKER_PASSWORD', 'GUTCARE_TEST_ANALYSIS_WORKER_PASSWORD',
    'GUTCARE_TEST_NOTIFICATION_WORKER_PASSWORD', 'GUTCARE_TEST_PRIVACY_WORKER_PASSWORD', 'GUTCARE_E2E_REDIS_PASSWORD',
    'MIGRATOR_DATABASE_URL', 'DATABASE_URL', 'REDIS_URL', 'MAIL_SMTP_HOST', 'MAIL_SMTP_PORT', 'MAIL_SENDER',
    'MAIL_STARTTLS', 'AUTH_EMAIL_LOOKUP_PEPPER', 'AUTH_EMAIL_ENCRYPTION_KEY', 'AUTH_JWT_SIGNING_KEY', 'APP_ENV',
    'GUTCARE_AUTH_E2E_BRIDGE', 'GUTCARE_AUTH_E2E_BRIDGE_STOP_TOKEN', 'GUTCARE_AUTH_E2E_NO_DOTENV',
    'GUTCARE_AUTH_E2E_ALEMBIC_CONFIG', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE',
    'PRIVACY_POLICY_VERSION', 'PRIVACY_POLICY_SUMMARY_HASH', 'HEALTH_DATA_PROCESSING_POLICY_VERSION',
    'HEALTH_DATA_PROCESSING_SUMMARY_HASH', 'GUTCARE_LIVE_E2E_BASE_URL', 'GUTCARE_LIVE_E2E_EMAIL',
    'GUTCARE_LIVE_E2E_PASSWORD', 'GUTCARE_LIVE_E2E_PROFILE_ID', 'PSYCOPG_IMPL'
)
$previousEnv = @{}
foreach ($name in $envNames) { $previousEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
$composeStarted = $false
$apiProcess = $null
$httpClient = [System.Net.Http.HttpClient]::new()
$logRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$stdoutPath = [System.IO.Path]::GetFullPath((Join-Path $logRoot "gutcare-auth-e2e-$runId.stdout.log"))
$stderrPath = [System.IO.Path]::GetFullPath((Join-Path $logRoot "gutcare-auth-e2e-$runId.stderr.log"))

try {
    New-Item -ItemType Directory -Path $runWorkDir | Out-Null
    if (Test-Path -LiteralPath (Join-Path $runWorkDir '.env') -PathType Leaf) {
        throw 'Temporary E2E working directory unexpectedly contains a .env file.'
    }
    $env:GUTCARE_TEST_PG18_HOST_PORT = [string]$ports.pg
    $env:GUTCARE_E2E_REDIS_HOST_PORT = [string]$ports.redis
    $env:GUTCARE_E2E_MAILPIT_SMTP_HOST_PORT = [string]$ports.smtp
    $env:GUTCARE_E2E_MAILPIT_API_HOST_PORT = [string]$ports.mailpit
    $env:GUTCARE_TEST_BOOTSTRAP_PASSWORD = $bootstrapPassword
    $env:GUTCARE_TEST_MIGRATOR_PASSWORD = $migratorPassword
    $env:GUTCARE_TEST_APP_PASSWORD = $appPassword
    $env:GUTCARE_TEST_WORKER_PASSWORD = $workerPassword
    $env:GUTCARE_TEST_ANALYSIS_WORKER_PASSWORD = $analysisPassword
    $env:GUTCARE_TEST_NOTIFICATION_WORKER_PASSWORD = $notificationPassword
    $env:GUTCARE_TEST_PRIVACY_WORKER_PASSWORD = $privacyPassword
    $env:GUTCARE_E2E_REDIS_PASSWORD = $redisPassword

    $composeArgs = @('compose', '-f', 'compose.integration.yaml', '-p', $project, 'up', '-d', '--wait', 'postgres-integration', 'redis-auth-e2e', 'mailpit-auth-e2e')
    $composeStarted = $true
    $null = & $docker.Source @composeArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw 'Isolated PG18/Redis/Mailpit Compose startup failed; output suppressed.' }
    Write-Host 'isolated services ready: PostgreSQL 18, Redis, Mailpit'

    $python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
    $uv = & (Join-Path $PSScriptRoot 'resolve-uv.ps1')
    if (-not $python -or -not $uv) { throw 'Pinned Python/uv runtime is unavailable.' }
    $env:MIGRATOR_DATABASE_URL = "postgresql+psycopg://gutcare_migrator:$migratorPassword@127.0.0.1:$($ports.pg)/gutcare_business_test"
    $env:DATABASE_URL = "postgresql+psycopg://gutcare_app:$appPassword@127.0.0.1:$($ports.pg)/gutcare_business_test"
    $env:REDIS_URL = "redis://:$redisPassword@127.0.0.1:$($ports.redis)/0"
    $env:MAIL_SMTP_HOST = '127.0.0.1'
    $env:MAIL_SMTP_PORT = [string]$ports.smtp
    $env:MAIL_SENDER = 'no-reply@gutcare.invalid'
    $env:MAIL_STARTTLS = 'false'
    $env:AUTH_EMAIL_LOOKUP_PEPPER = $pepper
    $env:AUTH_EMAIL_ENCRYPTION_KEY = $emailEncryptionKey
    $env:AUTH_JWT_SIGNING_KEY = $jwtKey
    $env:APP_ENV = 'local'
    $env:GUTCARE_AUTH_E2E_BRIDGE = '1'
    $env:GUTCARE_AUTH_E2E_BRIDGE_STOP_TOKEN = $script:bridgeStopToken
    $env:GUTCARE_AUTH_E2E_NO_DOTENV = '1'
    $env:GUTCARE_AUTH_E2E_ALEMBIC_CONFIG = Join-Path $root 'backend\alembic.ini'
    $env:PYTHONPATH = Join-Path $root 'backend\src'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PRIVACY_POLICY_VERSION = [string]$privacyNotice.policy_version
    $env:PRIVACY_POLICY_SUMMARY_HASH = [string]$privacyNotice.summary_sha256
    $env:HEALTH_DATA_PROCESSING_POLICY_VERSION = [string]$healthNotice.policy_version
    $env:HEALTH_DATA_PROCESSING_SUMMARY_HASH = [string]$healthNotice.summary_sha256

    Push-Location $runWorkDir
    try {
        $migrationOutput = @(& $uv run --locked --project (Join-Path $root 'backend') --python $python python -c "import os; from pathlib import Path; from alembic.config import Config; from alembic import command; config=Config(os.environ['GUTCARE_AUTH_E2E_ALEMBIC_CONFIG']); config.set_main_option('script_location', str(Path(os.environ['GUTCARE_AUTH_E2E_ALEMBIC_CONFIG']).parent / 'migrations')); config.attributes['skip_file_config']=True; command.upgrade(config, 'head')" 2>&1)
        if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed: $(Get-SafeCapturedDiagnostic $migrationOutput)" }
    } finally { Pop-Location }
    Write-Host 'Alembic upgrade head complete'

    $backendPython = Join-Path $root 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $backendPython -PathType Leaf)) { throw 'Backend locked environment is missing.' }
    $bridgePath = Join-Path $root 'backend\tests\auth_e2e_http_bridge.py'
    $apiProcess = Start-Process -FilePath $backendPython -ArgumentList @(
        ('"' + $bridgePath + '"'), [string]$ports.api
    ) -WorkingDirectory $runWorkDir -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    $baseUrl = "http://127.0.0.1:$($ports.api)"
    $baseUrlMailpit = "http://127.0.0.1:$($ports.mailpit)"
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($apiProcess.HasExited) { throw "Backend process exited before readiness (exit=$($apiProcess.ExitCode)): $(Get-SafeStartupDiagnostic)" }
        try {
            $health = Invoke-Http $baseUrl '/health/live'
            if ($health.Status -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw 'Backend readiness timeout; diagnostic output suppressed.' }
    Write-Host 'backend health/live HTTP 200'

    $registration = {
        param([string]$Email, [string]$Password)
        Invoke-Http $baseUrl '/api/v1/auth/register' 'POST' @{
            email = $Email; password = $Password; birth_year = 1990
            privacy_policy_version = [string]$privacyNotice.policy_version
            health_data_processing_consent = $true
            health_data_processing_policy_version = [string]$healthNotice.policy_version
        }
    }
    $registerA = & $registration $emailA $authPassword
    Assert-Status $registerA 202 'A register'
    $verifyA = Get-MailToken $baseUrlMailpit $emailA 'GutCare 邮箱验证'
    $verifyAResponse = Invoke-Http $baseUrl '/api/v1/auth/email/verify' 'POST' @{ token = $verifyA }
    Assert-Status $verifyAResponse 204 'A email verify'

    $loginA = Invoke-Http $baseUrl '/api/v1/auth/login' 'POST' @{ email = $emailA; password = $authPassword }
    Assert-Status $loginA 200 'A login'
    $profileA = Invoke-Http $baseUrl '/api/v1/patients/me' 'GET' $null ([string]$loginA.Body.access_token)
    Assert-Status $profileA 200 'A GET profile'
    $profileAId = [string]$profileA.Body.id

    $oldRefresh = [string]$loginA.Body.refresh_token
    $rotated = Invoke-Http $baseUrl '/api/v1/auth/refresh' 'POST' @{ refresh_token = $oldRefresh }
    Assert-Status $rotated 200 'A refresh rotation'
    $oldRefreshReplay = Invoke-Http $baseUrl '/api/v1/auth/refresh' 'POST' @{ refresh_token = $oldRefresh }
    Assert-Problem $oldRefreshReplay 401 'A old refresh rejection'
    # Refresh-family replay revokes the winning successor; use a fresh login for logout.
    $logoutLogin = Invoke-Http $baseUrl '/api/v1/auth/login' 'POST' @{ email = $emailA; password = $authPassword }
    Assert-Status $logoutLogin 200 'A fresh login for logout'
    $logout = Invoke-Http $baseUrl '/api/v1/auth/logout' 'POST' @{} ([string]$logoutLogin.Body.access_token)
    Assert-Status $logout 204 'A logout'
    $loggedOutRefresh = Invoke-Http $baseUrl '/api/v1/auth/refresh' 'POST' @{ refresh_token = [string]$logoutLogin.Body.refresh_token }
    Assert-Problem $loggedOutRefresh 401 'A refresh after logout'

    $preResetLogin = Invoke-Http $baseUrl '/api/v1/auth/login' 'POST' @{ email = $emailA; password = $authPassword }
    Assert-Status $preResetLogin 200 'A login before password reset'
    $resetExisting = Invoke-Http $baseUrl '/api/v1/auth/password/reset/request' 'POST' @{ email = $emailA }
    $resetUnknown = Invoke-Http $baseUrl '/api/v1/auth/password/reset/request' 'POST' @{ email = $unknownEmail }
    Assert-Status $resetExisting 202 'reset request existing account'
    Assert-Status $resetUnknown 202 'reset request unknown account'
    $existingKeys = @($resetExisting.Body.PSObject.Properties.Name | Sort-Object)
    $unknownKeys = @($resetUnknown.Body.PSObject.Properties.Name | Sort-Object)
    if (($existingKeys -join ',') -ne ($unknownKeys -join ',') -or
        $existingKeys -notcontains 'status' -or
        $resetExisting.Body.status -ne 'accepted' -or
        $resetUnknown.Body.status -ne 'accepted') { throw 'Password-reset external response shape differed.' }
    Write-Host 'password-reset responses: same HTTP/status/schema shape'

    $resetToken = Get-MailToken $baseUrlMailpit $emailA 'GutCare 密码重置'
    $confirmReset = Invoke-Http $baseUrl '/api/v1/auth/password/reset/confirm' 'POST' @{ token = $resetToken; new_password = $newPassword }
    Assert-Status $confirmReset 204 'password reset confirm'
    $preResetRefresh = Invoke-Http $baseUrl '/api/v1/auth/refresh' 'POST' @{ refresh_token = [string]$preResetLogin.Body.refresh_token }
    Assert-Problem $preResetRefresh 401 'pre-reset refresh invalidation'
    $newPasswordLogin = Invoke-Http $baseUrl '/api/v1/auth/login' 'POST' @{ email = $emailA; password = $newPassword }
    Assert-Status $newPasswordLogin 200 'login with reset password'

    $patchNick = Invoke-Http $baseUrl '/api/v1/patients/me' 'PATCH' @{ profile_version = [int]$profileA.Body.profile_version; nickname = 'synthetic-a' } ([string]$newPasswordLogin.Body.access_token)
    Assert-Status $patchNick 200 'A profile PATCH explicit nickname'
    if ($patchNick.Body.nickname -ne 'synthetic-a' -or $patchNick.Body.profile_version -ne 2) { throw 'Explicit profile patch result did not match expected state.' }
    $clearNick = Invoke-Http $baseUrl '/api/v1/patients/me' 'PATCH' @{ profile_version = 2; nickname = $null } ([string]$newPasswordLogin.Body.access_token)
    Assert-Status $clearNick 200 'A profile PATCH explicit null'
    if ($null -ne $clearNick.Body.nickname -or $clearNick.Body.profile_version -ne 3) { throw 'Explicit null profile patch result did not match expected state.' }
    $stalePatch = Invoke-Http $baseUrl '/api/v1/patients/me' 'PATCH' @{ profile_version = 2; timezone = 'Asia/Tokyo' } ([string]$newPasswordLogin.Body.access_token)
    Assert-Problem $stalePatch 409 'A stale profile PATCH'

    $registerB = & $registration $emailB $authPassword
    Assert-Status $registerB 202 'B register'
    $verifyB = Get-MailToken $baseUrlMailpit $emailB 'GutCare 邮箱验证'
    $verifyBResponse = Invoke-Http $baseUrl '/api/v1/auth/email/verify' 'POST' @{ token = $verifyB }
    Assert-Status $verifyBResponse 204 'B email verify'
    $loginB = Invoke-Http $baseUrl '/api/v1/auth/login' 'POST' @{ email = $emailB; password = $authPassword }
    Assert-Status $loginB 200 'B login'
    $profileB = Invoke-Http $baseUrl '/api/v1/patients/me' 'GET' $null ([string]$loginB.Body.access_token)
    Assert-Status $profileB 200 'B GET profile'
    if ($profileAId -eq [string]$profileB.Body.id) { throw 'Synthetic A/B profiles unexpectedly shared an identity.' }
    $identityProbe = Invoke-Http $baseUrl ("/api/v1/patients/me?patient_id={0}" -f [uri]::EscapeDataString([string]$profileB.Body.id)) 'GET' $null ([string]$newPasswordLogin.Body.access_token)
    Assert-Status $identityProbe 200 'A identity-scoped profile probe'
    if ([string]$identityProbe.Body.id -ne $profileAId) { throw 'A profile response was not scoped to A credentials.' }
    $forgedProfile = Invoke-Http $baseUrl '/api/v1/patients/me' 'PATCH' @{ profile_version = 3; nickname = 'forged'; patient_id = [string]$profileB.Body.id } ([string]$newPasswordLogin.Body.access_token)
    Assert-Problem $forgedProfile 422 'A forged patient_id rejection'
    $bAfter = Invoke-Http $baseUrl '/api/v1/patients/me' 'GET' $null ([string]$loginB.Body.access_token)
    Assert-Status $bAfter 200 'B profile isolation recheck'
    if ([string]$bAfter.Body.id -ne [string]$profileB.Body.id -or $null -ne $bAfter.Body.nickname) { throw 'A request changed or exposed B profile state.' }

    # The APP adapters run against this real backend; only the native token store is an explicit memory fake.
    $node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
    if (-not $node) { throw 'Pinned Node runtime is unavailable for APP live contract verification.' }
    $env:GUTCARE_LIVE_E2E_BASE_URL = $baseUrl
    $env:GUTCARE_LIVE_E2E_EMAIL = $emailB
    $env:GUTCARE_LIVE_E2E_PASSWORD = $authPassword
    $env:GUTCARE_LIVE_E2E_PROFILE_ID = [string]$profileB.Body.id
    $vitestCli = Join-Path $root 'app\node_modules\vitest\vitest.mjs'
    $vitestConfig = Join-Path $root 'app\vitest.config.ts'
    $liveTest = Join-Path $root 'app\tests\authLiveE2e.test.ts'
    Push-Location $runWorkDir
    try {
        $null = & $node $vitestCli run --root (Join-Path $root 'app') --config $vitestConfig $liveTest 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'APP AuthApi/ProfileApi/SessionService live contract chain failed; output suppressed.' }
    } finally { Pop-Location }
    Write-Host 'APP AuthApi/ProfileApi/SessionService live chain passed (memory-only test adapter)'
    Write-Host 'B01-4 authentication E2E completed; synthetic profile IDs remained in memory only.'
} finally {
    if ($null -ne $apiProcess) {
        $current = Get-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue
        if ($current -and $current.StartTime -eq $apiProcess.StartTime) {
            if ($baseUrl) {
                try { $null = Invoke-Http $baseUrl '/__test/shutdown' 'POST' } catch { }
                try { Wait-Process -Id $apiProcess.Id -Timeout 10 -ErrorAction Stop } catch { }
            }
            $current = Get-Process -Id $apiProcess.Id -ErrorAction SilentlyContinue
            if ($current -and $current.StartTime -eq $apiProcess.StartTime) {
                Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
                Wait-Process -Id $apiProcess.Id -Timeout 10 -ErrorAction SilentlyContinue
            }
        }
    }
    if ($composeStarted) {
        $members = @(& $docker.Source ps -aq --filter "label=com.docker.compose.project=$project")
        foreach ($containerId in $members) {
            if (-not $containerId) { continue }
            $label = & $docker.Source inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' $containerId
            if ([string]$label -ne $project) { throw 'Refusing cleanup: a container did not match this E2E Compose project.' }
        }
        $null = & $docker.Source compose -f 'compose.integration.yaml' -p $project --profile auth-e2e down --remove-orphans --volumes --rmi local 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'Scoped E2E Compose cleanup failed.' }
        $remaining = @(& $docker.Source ps -aq --filter "label=com.docker.compose.project=$project")
        if ($remaining.Count -gt 0 -and $remaining[0]) { throw 'Scoped E2E containers remain after cleanup.' }
    }
    $httpClient.Dispose()
    foreach ($path in @($stdoutPath, $stderrPath)) {
        $resolved = [System.IO.Path]::GetFullPath($path)
        if (-not $resolved.StartsWith($logRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
            [System.IO.Path]::GetFileName($resolved) -notmatch "^gutcare-auth-e2e-$runId\.(stdout|stderr)\.log$") {
            throw 'Refusing cleanup of an unverified log path.'
        }
        if (Test-Path -LiteralPath $resolved -PathType Leaf) { Remove-Item -LiteralPath $resolved -Force }
    }
    if (Test-Path -LiteralPath $runWorkDir -PathType Container) {
        $resolvedWorkDir = [System.IO.Path]::GetFullPath($runWorkDir)
        if ([System.IO.Path]::GetDirectoryName($resolvedWorkDir) -ne $tempRoot -or
            [System.IO.Path]::GetFileName($resolvedWorkDir) -ne "gutcare-auth-e2e-$runId-work") {
            throw 'Refusing cleanup of an unverified E2E working directory.'
        }
        Remove-Item -LiteralPath $resolvedWorkDir -Recurse -Force
    }
    foreach ($name in $envNames) { [Environment]::SetEnvironmentVariable($name, $previousEnv[$name], 'Process') }
}
