[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$api = 'http://127.0.0.1:8000'
$mailpit = 'http://127.0.0.1:8025'
$http = [System.Net.Http.HttpClient]::new()
$today = (Get-Date).ToString('yyyy-MM-dd')
$start = (Get-Date).AddDays(-7).ToString('yyyy-MM-dd')
$end = (Get-Date).AddDays(1).ToString('yyyy-MM-dd')

function Invoke-Api([string]$Method, [string]$Path, [object]$Body = $null, [string]$Bearer = $null, [string]$Key = $null) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), "$api$Path")
    $request.Headers.Accept.ParseAdd('application/json')
    $request.Headers.Accept.ParseAdd('application/problem+json')
    if ($Bearer) { $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Bearer) }
    if ($Key) { $request.Headers.Add('Idempotency-Key', $Key) }
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
    } catch { throw "Request failed: $Method; endpoint and transport details suppressed." }
    finally { $request.Dispose() }
}

function Assert-Status($Response, [int]$Expected, [string]$Stage) {
    if ($Response.Status -ne $Expected) {
        $code = if ($Response.Body -and $Response.Body.code) { " code=$($Response.Body.code)" } else { '' }
        throw "$Stage expected HTTP $Expected, got $($Response.Status).$code Response body suppressed."
    }
    Write-Host "$Stage HTTP $Expected"
}

function Invoke-Mailpit([string]$Path) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, "$mailpit$Path")
    try {
        $response = $http.SendAsync($request).GetAwaiter().GetResult()
        try {
            if (-not $response.IsSuccessStatusCode) { throw 'Mailpit returned a non-success response.' }
            return ConvertFrom-Json -InputObject ($response.Content.ReadAsStringAsync().GetAwaiter().GetResult())
        } finally { $response.Dispose() }
    } catch { throw 'Mailpit request failed; endpoint, message contents, and response details suppressed.' }
    finally { $request.Dispose() }
}

function Get-VerificationToken([string]$Email) {
    $deadline = (Get-Date).AddSeconds(30)
    while ($true) {
        $listing = Invoke-Mailpit '/api/v1/messages?limit=50'
        foreach ($item in @($listing.messages)) {
            $to = ConvertTo-Json -InputObject $item.To -Depth 8 -Compress
            if ($to -notmatch [regex]::Escape($Email) -or $item.Subject -ne 'GutCare 邮箱验证') { continue }
            $messageId = if ($item.ID) { $item.ID } else { $item.Id }
            if (-not $messageId) { continue }
            $detail = Invoke-Mailpit "/api/v1/message/$([uri]::EscapeDataString([string]$messageId))"
            $mailText = if ($detail.Text) { [string]$detail.Text } else { [string]$detail.Message.Text }
            $match = [regex]::Match($mailText, '(?m)^\s*([A-Za-z0-9_-]{60,})\s*$')
            if ($match.Success) { return $match.Groups[1].Value }
        }
        if ((Get-Date) -ge $deadline) { break }
        Start-Sleep -Milliseconds 300
    }
    throw 'Mailpit did not provide the synthetic verification message; message contents suppressed.'
}

function New-SyntheticAccount([string]$Tag) {
    $suffix = [guid]::NewGuid().ToString('N')
    $email = "gutcare-p1-$Tag-$suffix@example.com"
    $password = "Demo-p1-$([guid]::NewGuid().ToString('N'))"
    $registered = Invoke-Api 'POST' '/api/v1/auth/register' @{
        email = $email; password = $password; birth_year = 1990
        privacy_policy_version = 'test-only-privacy-v1'
        health_data_processing_consent = $true
        health_data_processing_policy_version = 'test-only-health-v1'
    }
    Assert-Status $registered 202 "$Tag registration"
    $verify = Invoke-Api 'POST' '/api/v1/auth/email/verify' @{ token = (Get-VerificationToken $email) }
    Assert-Status $verify 204 "$Tag email verification"
    $login = Invoke-Api 'POST' '/api/v1/auth/login' @{ email = $email; password = $password }
    Assert-Status $login 200 "$Tag login"
    return [string]$login.Body.access_token
}

function Grant-AvailableConsent([string]$Bearer, [string]$ConsentType, [bool]$Grant) {
    $notice = Invoke-Api 'GET' "/api/v1/consent-notices?consent_type=$ConsentType" $null $Bearer
    Assert-Status $notice 200 "$ConsentType notice"
    if (-not $notice.Body.enabled -or -not $notice.Body.policy_version) { return $false }
    $saved = Invoke-Api 'POST' '/api/v1/patients/me/consents' @{
        consent_type = $ConsentType; policy_version = $notice.Body.policy_version; granted = $Grant
    } $Bearer
    Assert-Status $saved 201 "$ConsentType consent"
    return $true
}

function Test-ApiAccess([string]$Bearer, [string]$Path) {
    $response = Invoke-Api 'GET' $Path $null $Bearer
    Assert-Status $response 200 'Authenticated API access'
    return $response.Body
}

try {
    Assert-Status (Invoke-Api 'GET' '/health/live') 200 'phone-demo health'

    $token = New-SyntheticAccount 'primary'
    $limitedToken = New-SyntheticAccount 'consent'
    $otherToken = $limitedToken
    if (-not (Grant-AvailableConsent $token 'mood_data_processing' $true)) { throw 'F14 mood data consent is disabled in phone-demo configuration.' }
    [void](Grant-AvailableConsent $token 'mood_ai_sharing' $true)
    [void](Grant-AvailableConsent $token 'third_party_ai' $true)

    # F06: plan lifecycle, schedule generation, same-day check-in, history, stale-write 409.
    $planResponse = Invoke-Api 'POST' '/api/v1/medication-plans' @{
        medication_name = '合成演示药物'; dosage_text = '按医嘱'; source_type = 'manual'; start_date = $today
    } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $planResponse 201 'F06 create plan'
    $planId = [string]$planResponse.Body.id
    $transition = Invoke-Api 'POST' "/api/v1/medication-plans/$planId/transitions" @{ record_version = 1; action = 'confirm' } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $transition 200 'F06 confirm plan'
    $transition = Invoke-Api 'POST' "/api/v1/medication-plans/$planId/transitions" @{ record_version = 2; action = 'activate' } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $transition 200 'F06 activate plan'
    $schedule = Invoke-Api 'POST' "/api/v1/medication-plans/$planId/schedules" @{
        local_time = '12:00:00'; timezone = 'Asia/Shanghai'; valid_from = $today; enabled = $true
    } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $schedule 201 'F06 create schedule'
    $scheduleId = [string]$schedule.Body.id
    $materializer = Get-Content (Join-Path $root 'phone-demo.env') | Where-Object { $_ -match '^GUTCARE_WORKER_PASSWORD=' } | Select-Object -First 1
    if (-not $materializer) { throw 'Phone-demo worker configuration is missing.' }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw 'Docker CLI is unavailable.' }
    & $docker.Source compose --profile e2e -f (Join-Path $root 'compose.phone-demo.yaml') --env-file (Join-Path $root 'phone-demo.env') run --rm medication-materializer | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'F06 materializer failed; command output suppressed.' }
    $todayCheckins = Test-ApiAccess $token '/api/v1/medication-checkins/today'
    $checkin = @($todayCheckins | Where-Object { $_.schedule_id -eq $scheduleId }) | Select-Object -First 1
    if (-not $checkin) { throw 'F06 expected a generated same-day medication check-in.' }
    $checkinResponse = Invoke-Api 'PATCH' "/api/v1/medication-checkins/$($checkin.id)" @{
        record_version = [int]$checkin.record_version; status = 'taken'; taken_at = (Get-Date).ToUniversalTime().ToString('o')
    } $token
    Assert-Status $checkinResponse 200 'F06 mark taken'
    $history = Test-ApiAccess $token "/api/v1/medication-checkins?start=$start&end=$end"
    if (-not (@($history | Where-Object id -eq $checkin.id))) { throw 'F06 check-in missing from history.' }
    Assert-Status (Invoke-Api 'PATCH' "/api/v1/medication-checkins/$($checkin.id)" @{
        record_version = [int]$checkin.record_version; status = 'not_taken'
    } $token) 409 'F06 stale check-in version'
    Assert-Status (Invoke-Api 'DELETE' "/api/v1/medication-plans/$planId`?record_version=$($transition.Body.record_version)" $null $token) 204 'F06 cleanup plan'

    # F10: use a real structured symptom record to trigger the phone-demo synthetic fixture.
    $symptom = Invoke-Api 'POST' '/api/v1/symptom-records' @{
        occurred_at = (Get-Date).ToUniversalTime().ToString('o')
        payload = @{ items = @(@{ symptom_code = 'other'; other_description = '合成演示症状'; severity = 1 }) }
    } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $symptom 201 'F10 create synthetic symptom'
    $alerts = Test-ApiAccess $token '/api/v1/risk-alerts?limit=20&unread_only=true'
    $alert = @($alerts.items | Where-Object { $_.message -like '*演示测试提示*' }) | Select-Object -First 1
    if (-not $alert -or $alert.environment -ne 'test_only') { throw 'F10 test_only rule did not produce an explicitly marked alert.' }
    Assert-Status (Invoke-Api 'GET' "/api/v1/risk-alerts/$($alert.id)" $null $token) 200 'F10 alert detail'
    Assert-Status (Invoke-Api 'GET' "/api/v1/risk-alerts/$($alert.id)" $null $otherToken) 404 'F10 cross-patient denial'
    Assert-Status (Invoke-Api 'POST' "/api/v1/risk-alerts/$($alert.id)/read" $null $token) 200 'F10 mark read'
    Assert-Status (Invoke-Api 'POST' "/api/v1/risk-alerts/$($alert.id)/reevaluate" $null $token) 200 'F10 reevaluate'

    # F11/F14: account with mood consent has deterministic trends and stable history pagination.
    $mood = Invoke-Api 'POST' '/api/v1/mood-records' @{
        occurred_at = (Get-Date).ToUniversalTime().ToString('o'); mood_level = 3; emotion_tags = @('calm')
    } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $mood 201 'F14 create mood record'
    $moodTrend = Test-ApiAccess $token "/api/v1/trends?from=$($start)T00:00:00%2B08:00&to=$($end)T00:00:00%2B08:00&bucket=day"
    if ($moodTrend.mood.availability -ne 'available') { throw 'F14 mood trend expected available with consent.' }
    $timeline = Test-ApiAccess $token "/api/v1/history/timeline?limit=2&since=$($start)T00:00:00%2B08:00&until=$($end)T00:00:00%2B08:00"
    if ($timeline.next_cursor) { [void](Test-ApiAccess $token "/api/v1/history/timeline?limit=2&since=$($start)T00:00:00%2B08:00&until=$($end)T00:00:00%2B08:00&cursor=$([uri]::EscapeDataString([string]$timeline.next_cursor))") }
    $moodPage = Test-ApiAccess $token '/api/v1/mood-records?limit=1'
    if (-not $moodPage.items) { throw 'F14 mood record missing from history.' }

    # F11 consent_required, and verify mood trend is independent of mood_ai_sharing.
    $limitedTrend = Test-ApiAccess $limitedToken "/api/v1/trends?from=$($start)T00:00:00%2B08:00&to=$($end)T00:00:00%2B08:00&bucket=day"
    if ($limitedTrend.mood.availability -ne 'consent_required') { throw 'F11 missing mood consent must return consent_required.' }
    [void](Grant-AvailableConsent $limitedToken 'mood_data_processing' $true)
    $limitedTrend = Test-ApiAccess $limitedToken "/api/v1/trends?from=$($start)T00:00:00%2B08:00&to=$($end)T00:00:00%2B08:00&bucket=day"
    if ($limitedTrend.mood.availability -ne 'available') { throw 'F14 mood trends must not require AI sharing consent.' }

    # F08: preview/create/status/cancel; no agent worker is invoked. Retry while pending must conflict.
    $preview = Test-ApiAccess $token '/api/v1/analysis-tasks/preview?analysis_type=comprehensive_health_analysis'
    if ($null -eq $preview.mood_record_count_in_range) { throw 'F08 preview response is incomplete.' }
    $task = Invoke-Api 'POST' '/api/v1/analysis-tasks' @{ analysis_type = 'comprehensive_health_analysis' } $token ([guid]::NewGuid().ToString('N'))
    Assert-Status $task 202 'F08 create task'
    if ($task.Body.status -ne 'pending' -or $task.Body.result) { throw 'F08 create must remain pending with no Agent result.' }
    $taskStatus = Invoke-Api 'GET' "/api/v1/analysis-tasks/$($task.Body.id)" $null $token
    Assert-Status $taskStatus 200 'F08 task status'
    if ($taskStatus.Body.status -ne 'pending' -or $taskStatus.Body.result) { throw 'F08 task status must remain pending with no Agent result.' }
    Assert-Status (Invoke-Api 'POST' "/api/v1/analysis-tasks/$($task.Body.id)/retry" $null $token ([guid]::NewGuid().ToString('N'))) 409 'F08 retry pending conflict'
    $cancelled = Invoke-Api 'POST' "/api/v1/analysis-tasks/$($task.Body.id)/cancel" $null $token
    Assert-Status $cancelled 200 'F08 cancel task'
    if ($cancelled.Body.status -ne 'cancelled' -or $cancelled.Body.result) { throw 'F08 cancellation returned unexpected task state.' }

    # F09: real empty-state and auth check only; no synthetic advice is created.
    $advice = Test-ApiAccess $token '/api/v1/advice?limit=10'
    if ($advice.items.Count -ne 0) { throw 'F09 expected a true advice empty state; content suppressed.' }
    Assert-Status (Invoke-Api 'GET' '/api/v1/advice?limit=10') 401 'F09 unauthenticated access'

    # F13 export uses one account; account deletion uses a separate disposable synthetic account.
    $export = Invoke-Api 'POST' '/api/v1/privacy/exports' @{ categories = @('profile', 'consents') } $token
    Assert-Status $export 201 'F13 export preview'
    $confirmed = Invoke-Api 'POST' "/api/v1/privacy/exports/$($export.Body.export_id)" $null $token
    Assert-Status $confirmed 202 'F13 confirm export'
    $exportStatus = Test-ApiAccess $token "/api/v1/privacy/exports/$($export.Body.export_id)"
    if ($exportStatus.status -notin @('pending', 'processing', 'ready')) { throw 'F13 export is in an unexpected state.' }
    $exportList = Test-ApiAccess $token '/api/v1/privacy/exports'
    if (-not (@($exportList | Where-Object export_id -eq $export.Body.export_id))) { throw 'F13 export missing from account history.' }
    $consents = Test-ApiAccess $token '/api/v1/patients/me/consents'
    if (-not $consents) { throw 'F13 consent settings returned no statuses.' }
    $sharingConsent = @($consents | Where-Object consent_type -eq 'mood_ai_sharing' | Select-Object -Last 1)
    if ($sharingConsent.Count -gt 0 -and $sharingConsent[0].granted) {
        [void](Grant-AvailableConsent $token 'mood_ai_sharing' $false)
    }
    $deleteToken = New-SyntheticAccount 'deletion'
    $deletion = Invoke-Api 'POST' '/api/v1/patients/me/account-deletion' $null $deleteToken
    Assert-Status $deletion 202 'F13 deletion request'
    $deletionStatus = Invoke-Api 'POST' "/api/v1/privacy/deletion-operations/$($deletion.Body.operation_id)/status" @{ receipt = $deletion.Body.receipt }
    Assert-Status $deletionStatus 200 'F13 deletion status'

    Write-Host 'P1 phone-demo E2E passed; synthetic account identifiers, tokens, notes, request bodies, and response contents were not emitted.'
} finally { $http.Dispose() }
