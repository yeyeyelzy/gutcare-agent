[CmdletBinding()]
param([ValidateRange(30, 900)][int]$TimeoutSeconds = 180, [switch]$NoBuild, [switch]$ResumeExisting)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$api = 'http://127.0.0.1:8000'
$mailpit = 'http://127.0.0.1:8025'
$http = [System.Net.Http.HttpClient]::new()
$artifactDir = Join-Path $root ('.demo-output\f08-agent\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))

function Get-Value([object]$Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function Invoke-Api([string]$Method, [string]$Url, [object]$Body = $null,
                    [string]$Bearer = $null, [string]$IdempotencyKey = $null) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Url)
    $request.Headers.Accept.ParseAdd('application/json')
    $request.Headers.Accept.ParseAdd('application/problem+json')
    if ($Bearer) { $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Bearer) }
    if ($IdempotencyKey) { $request.Headers.Add('Idempotency-Key', $IdempotencyKey) }
    if ($null -ne $Body) {
        $request.Content = [System.Net.Http.StringContent]::new((ConvertTo-Json -InputObject $Body -Depth 12 -Compress), [System.Text.Encoding]::UTF8, 'application/json')
    }
    try {
        $response = $http.SendAsync($request).GetAwaiter().GetResult()
        try {
            $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $parsed = $null
            if ($raw) { try { $parsed = ConvertFrom-Json -InputObject $raw } catch { $parsed = $null } }
            return [pscustomobject]@{ Status = [int]$response.StatusCode; Body = $parsed }
        } finally { $response.Dispose() }
    } catch { throw "F08 demo request failed during $Method; credentials and response content suppressed." }
    finally { $request.Dispose() }
}

function Assert-Status([object]$Response, [int]$Expected, [string]$Stage) {
    if ($Response.Status -ne $Expected) {
        $code = [string](Get-Value $Response.Body 'code')
        $suffix = if ($code) { " code=$code" } else { '' }
        throw "$Stage expected HTTP $Expected, got $($Response.Status).$suffix Response body suppressed."
    }
    Write-Host "$Stage HTTP $Expected"
}

function Get-MailToken([string]$Email, [string]$Subject) {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $listingResponse = Invoke-Api 'GET' "$mailpit/api/v1/messages?limit=50"
        if ($listingResponse.Status -eq 200) {
            foreach ($item in @(Get-Value $listingResponse.Body 'messages')) {
                $recipientJson = ConvertTo-Json -InputObject (Get-Value $item 'To') -Depth 8 -Compress
                if ($recipientJson -notmatch [regex]::Escape($Email) -or (Get-Value $item 'Subject') -ne $Subject) { continue }
                $messageId = [string](Get-Value $item 'ID')
                if (-not $messageId) { $messageId = [string](Get-Value $item 'Id') }
                if (-not $messageId) { continue }
                $detail = Invoke-Api 'GET' ("$mailpit/api/v1/message/{0}" -f [uri]::EscapeDataString($messageId))
                $bodyText = [string](Get-Value $detail.Body 'Text')
                if (-not $bodyText) { $bodyText = [string](Get-Value (Get-Value $detail.Body 'Message') 'Text') }
                $match = [regex]::Match($bodyText, '(?m)^\s*([A-Za-z0-9_-]{60,})\s*$')
                if ($match.Success) { return $match.Groups[1].Value }
            }
        }
        Start-Sleep -Milliseconds 350
    }
    throw 'Synthetic verification email unavailable; message content suppressed.'
}

try {
    if (-not $ResumeExisting) {
        & (Join-Path $PSScriptRoot 'phone-demo-agent-up.ps1') -NoBuild:$NoBuild
        if ($LASTEXITCODE -ne 0) { throw 'F08 mock Agent startup failed.' }
    }
    $health = Invoke-Api 'GET' "$api/health/live"
    Assert-Status $health 200 'Business API health'

    if ($ResumeExisting) {
        $mailList = Invoke-Api 'GET' "$mailpit/api/v1/messages?limit=50"
        $candidateEmails = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($item in @(Get-Value $mailList.Body 'messages')) {
            if ((Get-Value $item 'Subject') -ne 'GutCare 邮箱验证') { continue }
            foreach ($address in [regex]::Matches((ConvertTo-Json -InputObject (Get-Value $item 'To') -Depth 8 -Compress), 'gutcare-f08-[a-f0-9]{32}@example\.com')) {
                [void]$candidateEmails.Add($address.Value)
            }
        }
        if ($candidateEmails.Count -ne 1) { throw 'Expected exactly one existing synthetic F08 account; recipient details suppressed.' }
        $email = @($candidateEmails)[0]
        $password = "Demo-f08-resume-$([guid]::NewGuid().ToString('N'))"
        $resetRequest = Invoke-Api 'POST' "$api/api/v1/auth/password/reset/request" @{ email = $email }
        Assert-Status $resetRequest 202 'Existing synthetic account password reset request'
        $reset = Invoke-Api 'POST' "$api/api/v1/auth/password/reset/confirm" @{ token = (Get-MailToken $email 'GutCare 密码重置'); new_password = $password }
        Assert-Status $reset 204 'Existing synthetic account password reset'
    } else {
        $email = "gutcare-f08-$([guid]::NewGuid().ToString('N'))@example.com"
        $password = "Demo-f08-$([guid]::NewGuid().ToString('N'))"
        $registration = Invoke-Api 'POST' "$api/api/v1/auth/register" @{
            email = $email; password = $password; birth_year = 1990
            privacy_policy_version = 'test-only-privacy-v1'
            health_data_processing_consent = $true
            health_data_processing_policy_version = 'test-only-health-v1'
        }
        Assert-Status $registration 202 'Synthetic account registration'
        $verification = Invoke-Api 'POST' "$api/api/v1/auth/email/verify" @{ token = (Get-MailToken $email 'GutCare 邮箱验证') }
        Assert-Status $verification 204 'Synthetic email verification'
    }
    $login = Invoke-Api 'POST' "$api/api/v1/auth/login" @{ email = $email; password = $password }
    Assert-Status $login 200 'Synthetic account login'
    $accessToken = [string](Get-Value $login.Body 'access_token')
    if (-not $accessToken) { throw 'Login did not return an access session; response suppressed.' }

    if ($ResumeExisting) {
        $consents = Invoke-Api 'GET' "$api/api/v1/patients/me/consents" $null $accessToken
        Assert-Status $consents 200 'Existing synthetic account consent query'
        $hasAiConsent = @($consents.Body | Where-Object { $_.consent_type -eq 'third_party_ai' -and $_.granted })
        if ($hasAiConsent.Count -eq 0) { throw 'Existing synthetic account does not have the expected processing consent.' }
    } else {
        $aiConsent = Invoke-Api 'POST' "$api/api/v1/patients/me/consents" @{
            consent_type = 'third_party_ai'; policy_version = 'test-only-third-party-ai-v1'; granted = $true
        } $accessToken
        Assert-Status $aiConsent 201 'Synthetic AI-processing consent'
    }

    $symptom = Invoke-Api 'POST' "$api/api/v1/symptom-records" @{
        occurred_at = (Get-Date).ToUniversalTime().ToString('o')
        payload = @{ items = @(@{ symptom_code = 'other'; other_description = '合成 F08 测试记录'; severity = 1 }) }
    } $accessToken ([guid]::NewGuid().ToString('N'))
    Assert-Status $symptom 201 'Synthetic confirmed record'

    $taskResponse = Invoke-Api 'POST' "$api/api/v1/analysis-tasks" @{
        analysis_type = 'comprehensive_health_analysis'
    } $accessToken ([guid]::NewGuid().ToString('N'))
    Assert-Status $taskResponse 202 'F08 task creation'
    $taskId = [string](Get-Value $taskResponse.Body 'id')
    if (-not $taskId) { throw 'Created task identifier was missing; response suppressed.' }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $task = $null
    do {
        Start-Sleep -Seconds 2
        $query = Invoke-Api 'GET' "$api/api/v1/analysis-tasks/$taskId" $null $accessToken
        Assert-Status $query 200 'Patient task query'
        $task = $query.Body
        $status = [string](Get-Value $task 'status')
        Write-Host "F08 patient-visible state: $status"
    } while ($status -in @('pending', 'processing') -and (Get-Date) -lt $deadline)
    if ($status -notin @('succeeded', 'partial', 'needs_input')) {
        throw "F08 task did not reach a successful mock-analysis state before timeout; state=$status."
    }

    $summary = [ordered]@{
        outcome = 'passed'
        mode = 'mock'
        external_model_used = $false
        task_id = $taskId
        final_status = $status
        attempt = Get-Value $task 'attempt'
        input_summary = Get-Value $task 'input_summary'
        result_present = ($null -ne (Get-Value $task 'result'))
        completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    }
    New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
    $summaryPath = Join-Path $artifactDir 'summary.json'
    [System.IO.File]::WriteAllText($summaryPath, (ConvertTo-Json -InputObject $summary -Depth 8), [System.Text.UTF8Encoding]::new($false))
    Write-Host "F08 mock end-to-end passed. Redacted summary saved: $summaryPath"
} finally {
    if ($accessToken) { $accessToken = $null }
    if ($password) { $password = $null }
    if ($http) { $http.Dispose() }
}
