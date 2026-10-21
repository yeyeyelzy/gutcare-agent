[CmdletBinding()]
param(
    [ValidateRange(60, 900)][int]$TimeoutSeconds = 240,
    [ValidateSet('both', 'diet', 'stool')][string]$RecognitionType = 'both',
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$api = 'http://127.0.0.1:8000'
$mailpit = 'http://127.0.0.1:8025'
$http = [System.Net.Http.HttpClient]::new()
$artifactDir = Join-Path $root ('.demo-output\f03-f04-agent\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$oldMode = [Environment]::GetEnvironmentVariable('GCA_MODE', 'Process')
$oldFixture = [Environment]::GetEnvironmentVariable('GCA_TEST_IMAGE_CANDIDATES', 'Process')

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
    if ($Body -is [byte[]]) {
        $request.Content = [System.Net.Http.ByteArrayContent]::new($Body)
        $request.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new('image/jpeg')
    } elseif ($null -ne $Body) {
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
    } catch { throw "F03/F04 demo request failed during $Method; credentials and response content suppressed." }
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

function Get-MailToken([string]$Email) {
    $deadline = (Get-Date).AddSeconds(45)
    while ((Get-Date) -lt $deadline) {
        $listing = Invoke-Api 'GET' "$mailpit/api/v1/messages?limit=50"
        if ($listing.Status -eq 200) {
            foreach ($item in @(Get-Value $listing.Body 'messages')) {
                $recipient = ConvertTo-Json -InputObject (Get-Value $item 'To') -Depth 8 -Compress
                if ($recipient -notmatch [regex]::Escape($Email) -or (Get-Value $item 'Subject') -ne 'GutCare 邮箱验证') { continue }
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
    throw 'Synthetic verification email unavailable; message contents suppressed.'
}

function New-SyntheticJpeg {
    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::new(4, 4)
    $bitmap.SetPixel(0, 0, [System.Drawing.Color]::FromArgb(34, 89, 55))
    $stream = [System.IO.MemoryStream]::new()
    try {
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
        return $stream.ToArray()
    } finally { $stream.Dispose(); $bitmap.Dispose() }
}

function Add-SyntheticImage([string]$Purpose, [string]$Bearer, [byte[]]$ImageBytes, [string]$Suffix) {
    $upload = Invoke-Api 'POST' "$api/api/v1/files/uploads" @{
        purpose = $Purpose; file_name = "synthetic-$Suffix.jpg"; content_type = 'image/jpeg'; size_bytes = $ImageBytes.Length
    } $Bearer ("img-upload-" + $Suffix + '-' + [guid]::NewGuid().ToString('N'))
    Assert-Status $upload 201 "$Suffix upload session"
    $put = Invoke-Api 'PUT' ([string](Get-Value $upload.Body 'upload_url')) $ImageBytes $Bearer
    Assert-Status $put 204 "$Suffix same-origin upload"
    $complete = Invoke-Api 'POST' ("$api/api/v1/files/uploads/{0}/complete" -f (Get-Value $upload.Body 'upload_id')) $null $Bearer
    Assert-Status $complete 200 "$Suffix scan completion"
    if ((Get-Value $complete.Body 'storage_status') -ne 'available') { throw "$Suffix file is unavailable after scan." }
    return [string](Get-Value $complete.Body 'id')
}

function Start-Recognition([string]$RecordId, [string]$RecordRoute, [string]$Purpose, [string]$Bearer,
                           [int]$RecordVersion, [int]$ImageSetVersion) {
    $notice = Invoke-Api 'GET' ("$api/api/v1/record-image-recognition-disclosures?purpose={0}" -f $Purpose) $null $Bearer
    Assert-Status $notice 200 "$Purpose notice lookup"
    if ((Get-Value $notice.Body 'enabled') -ne $true) { throw "$Purpose notice is disabled; recognition did not start." }
    $ack = Invoke-Api 'POST' "$api/api/v1/record-image-recognition-disclosures" @{
        record_id = $RecordId; purpose = $Purpose; record_version = $RecordVersion
        image_set_version = $ImageSetVersion; policy_version = (Get-Value $notice.Body 'policy_version'); acknowledged = $true
    } $Bearer
    Assert-Status $ack 201 "$Purpose disclosure acknowledgement"
    $created = Invoke-Api 'POST' ("$api/api/v1/{0}/{1}/image-recognition-requests" -f $RecordRoute, $RecordId) @{
        record_version = $RecordVersion; image_set_version = $ImageSetVersion
        disclosure_token = (Get-Value $ack.Body 'disclosure_token')
    } $Bearer ("img-recognition-" + [guid]::NewGuid().ToString('N'))
    Assert-Status $created 202 "$Purpose request creation"
    return [string](Get-Value $created.Body 'id')
}

function Wait-ForCandidate([string]$RequestId, [string]$Bearer, [string]$Type) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $response = Invoke-Api 'GET' ("$api/api/v1/record-image-recognition-requests/{0}" -f $RequestId) $null $Bearer
        Assert-Status $response 200 "$Type candidate query"
        $state = [string](Get-Value $response.Body 'status')
        if ($state -in @('failed', 'no_candidates', 'cancelled', 'invalidated')) {
            throw "$Type mock task ended in $state; no candidate was accepted."
        }
    } while ($state -notin @('candidates_ready') -and (Get-Date) -lt $deadline)
    if ($state -ne 'candidates_ready') { throw "$Type mock task timed out before candidate callback." }
    $candidate = @((Get-Value $response.Body 'candidates') | Where-Object { (Get-Value $_ 'candidate_type') -eq $Type }) | Select-Object -First 1
    if (-not $candidate -or (Get-Value $candidate 'status') -ne 'pending') { throw "$Type pending synthetic candidate missing." }
    return [pscustomobject]@{ Request = $response.Body; Candidate = $candidate }
}

try {
    $env:GCA_MODE = 'mock'
    $env:GCA_TEST_IMAGE_CANDIDATES = '1'
    & (Join-Path $PSScriptRoot 'phone-demo-agent-up.ps1') -NoBuild:$NoBuild
    if ($LASTEXITCODE -ne 0) { throw 'Phone-demo Agent profile failed to start.' }

    Assert-Status (Invoke-Api 'GET' "$api/health/live") 200 'Business API health'
    $email = "gutcare-image-$([guid]::NewGuid().ToString('N'))@example.com"
    $password = "Demo-image-$([guid]::NewGuid().ToString('N'))"
    $registration = Invoke-Api 'POST' "$api/api/v1/auth/register" @{
        email = $email; password = $password; birth_year = 1990
        privacy_policy_version = 'test-only-privacy-v1'; health_data_processing_consent = $true
        health_data_processing_policy_version = 'test-only-health-v1'
    }
    Assert-Status $registration 202 'Synthetic account registration'
    Assert-Status (Invoke-Api 'POST' "$api/api/v1/auth/email/verify" @{ token = (Get-MailToken $email) }) 204 'Synthetic email verification'
    $login = Invoke-Api 'POST' "$api/api/v1/auth/login" @{ email = $email; password = $password }
    Assert-Status $login 200 'Synthetic account login'
    $accessToken = [string](Get-Value $login.Body 'access_token')
    if (-not $accessToken) { throw 'Patient access token missing; response suppressed.' }

    foreach ($consent in @(
        @{ consent_type = 'sensitive_image'; policy_version = 'test-only-image-v1'; granted = $true },
        @{ consent_type = 'third_party_ai'; policy_version = 'test-only-third-party-ai-v1'; granted = $true }
    )) {
        Assert-Status (Invoke-Api 'POST' "$api/api/v1/patients/me/consents" $consent $accessToken) 201 ("Synthetic consent " + $consent.consent_type)
    }

    $jpeg = New-SyntheticJpeg
    $dietRequest = $null
    $stoolRequest = $null
    $foodConfirmed = $false
    $stoolConfirmed = $false

    if ($RecognitionType -in @('both', 'diet')) {
        $diet = Invoke-Api 'POST' "$api/api/v1/diet-records" @{
            occurred_at = (Get-Date).ToUniversalTime().ToString('o'); payload = @{ text_description = '合成饮食图片测试记录' }
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $diet 201 'Synthetic diet record'
        $dietFile = Add-SyntheticImage 'diet_image' $accessToken $jpeg 'diet'
        $dietAttach = Invoke-Api 'POST' ("$api/api/v1/dietary-records/{0}/images" -f (Get-Value $diet.Body 'id')) @{
            file_object_id = $dietFile; record_version = (Get-Value $diet.Body 'record_version'); image_set_version = 1
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $dietAttach 201 'Diet image attachment'
        $dietRequest = Start-Recognition (Get-Value $diet.Body 'id') 'dietary-records' 'diet_image_recognition' $accessToken (Get-Value $dietAttach.Body 'record_version') (Get-Value $dietAttach.Body 'image_set_version')

        $food = Wait-ForCandidate $dietRequest $accessToken 'food_name'
        $foodDecision = Invoke-Api 'POST' ("$api/api/v1/record-image-candidates/{0}/decision" -f (Get-Value $food.Candidate 'id')) @{
            action = 'accept'; candidate_version = (Get-Value $food.Candidate 'candidate_version')
            record_version = (Get-Value $food.Request 'decision_record_version')
            image_set_version = (Get-Value $food.Request 'image_set_version')
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $foodDecision 204 'Patient confirmation of synthetic food_name candidate'
        $foodConfirmed = $true
    }

    if ($RecognitionType -in @('both', 'stool')) {
        $stool = Invoke-Api 'POST' "$api/api/v1/stool-records" @{
            occurred_at = (Get-Date).ToUniversalTime().ToString('o'); payload = @{ notes = '合成排便图片测试记录' }
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $stool 201 'Synthetic stool record'
        $stoolFile = Add-SyntheticImage 'stool_image' $accessToken $jpeg 'stool'
        $stoolAttach = Invoke-Api 'POST' ("$api/api/v1/stool-records/{0}/images" -f (Get-Value $stool.Body 'id')) @{
            file_object_id = $stoolFile; record_version = (Get-Value $stool.Body 'record_version'); image_set_version = 1
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $stoolAttach 201 'Stool image attachment'
        $stoolRequest = Start-Recognition (Get-Value $stool.Body 'id') 'stool-records' 'stool_image_recognition' $accessToken (Get-Value $stoolAttach.Body 'record_version') (Get-Value $stoolAttach.Body 'image_set_version')

        $bristol = Wait-ForCandidate $stoolRequest $accessToken 'bristol_type'
        $stoolDecision = Invoke-Api 'POST' ("$api/api/v1/record-image-candidates/{0}/decision" -f (Get-Value $bristol.Candidate 'id')) @{
            action = 'accept'; candidate_version = (Get-Value $bristol.Candidate 'candidate_version')
            record_version = (Get-Value $bristol.Request 'decision_record_version')
            image_set_version = (Get-Value $bristol.Request 'image_set_version')
        } $accessToken ([guid]::NewGuid().ToString('N'))
        Assert-Status $stoolDecision 204 'Patient confirmation of synthetic Bristol candidate'
        $stoolConfirmed = $true
    }

    New-Item -ItemType Directory -Path $artifactDir -Force | Out-Null
    $summary = [ordered]@{
        outcome = 'passed'; mode = 'mock'; synthetic_image_candidate_fixture = $true
        external_model_used = $false
        recognition_type = $RecognitionType
        diet_request_id = $dietRequest; diet_candidate_type = if ($dietRequest) { 'food_name' } else { $null }; diet_patient_confirmed = $foodConfirmed
        stool_request_id = $stoolRequest; stool_candidate_type = if ($stoolRequest) { 'bristol_type' } else { $null }; stool_patient_confirmed = $stoolConfirmed
        completed_at_utc = (Get-Date).ToUniversalTime().ToString('o')
    }
    $summaryPath = Join-Path $artifactDir 'summary.json'
    [System.IO.File]::WriteAllText($summaryPath, (ConvertTo-Json -InputObject $summary -Depth 6), [System.Text.UTF8Encoding]::new($false))
    Write-Host "F03/F04 synthetic mock E2E passed. Redacted summary saved: $summaryPath"
} finally {
    if ($accessToken) { $accessToken = $null }
    if ($password) { $password = $null }
    if ($oldMode) { $env:GCA_MODE = $oldMode } else { Remove-Item Env:GCA_MODE -ErrorAction SilentlyContinue }
    if ($oldFixture) { $env:GCA_TEST_IMAGE_CANDIDATES = $oldFixture } else { Remove-Item Env:GCA_TEST_IMAGE_CANDIDATES -ErrorAction SilentlyContinue }
    $http.Dispose()
}
