[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
$project = 'gutcare-competition-demo'
$api = 'http://127.0.0.1:8000'
$mailpit = 'http://127.0.0.1:8025'
$client = [System.Net.Http.HttpClient]::new()

function Get-Field([object]$Value, [string]$Name) {
    if ($null -eq $Value) { return $null }
    $property = $Value.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function Invoke-Api([string]$Method, [string]$Url, [object]$Body = $null, [string]$Bearer = $null, [string]$IdempotencyKey = $null) {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::new($Method), $Url)
    $request.Headers.Accept.ParseAdd('application/json')
    $request.Headers.Accept.ParseAdd('application/problem+json')
    if ($Bearer) { $request.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new('Bearer', $Bearer) }
    if ($IdempotencyKey) { $request.Headers.Add('Idempotency-Key', $IdempotencyKey) }
    if ($Body -is [byte[]]) {
        $request.Content = [System.Net.Http.ByteArrayContent]::new($Body)
        $request.Content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new('image/jpeg')
    } elseif ($null -ne $Body) {
        $json = ConvertTo-Json -InputObject $Body -Depth 12 -Compress
        $request.Content = [System.Net.Http.StringContent]::new($json, [System.Text.Encoding]::UTF8, 'application/json')
    }
    try {
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        try {
            $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            $parsed = $null
            if ($raw) { try { $parsed = ConvertFrom-Json -InputObject $raw } catch { $parsed = $raw } }
            return [pscustomobject]@{
                Status = [int]$response.StatusCode
                Body = $parsed
                Bytes = if ($Method -eq 'GET' -and $response.Content.Headers.ContentType.MediaType -eq 'image/jpeg') { $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult() } else { $null }
            }
        } finally { $response.Dispose() }
    } catch {
        throw "F02 demo request failed during $Method. Endpoint details and response body suppressed."
    } finally { $request.Dispose() }
}

function Assert-Status([object]$Response, [int]$Expected, [string]$Stage) {
    if ($Response.Status -ne $Expected) {
        $safeDetails = @()
        foreach ($issue in @(Get-Field $Response.Body 'errors')) {
            $location = @(Get-Field $issue 'location') -join '.'
            $kind = [string](Get-Field $issue 'code')
            if ($location -or $kind) { $safeDetails += "${location}:$kind" }
        }
        $errorCode = [string](Get-Field $Response.Body 'code')
        $details = if ($safeDetails.Count -gt 0) { ' fields=' + ($safeDetails -join ',') } elseif ($errorCode) { " code=$errorCode" } else { '' }
        throw "$Stage failed: expected HTTP $Expected, received $($Response.Status).$details Response body suppressed."
    }
    Write-Host "$Stage HTTP $Expected"
}

function Get-MailToken([string]$Recipient) {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $listing = Invoke-Api 'GET' "$mailpit/api/v1/messages?limit=50"
        if ($listing.Status -ne 200) { throw 'Mailpit listing failed; response body suppressed.' }
        foreach ($item in @(Get-Field $listing.Body 'messages')) {
            $toText = ConvertTo-Json -InputObject (Get-Field $item 'To') -Depth 8 -Compress
            if ($toText -notmatch [regex]::Escape($Recipient) -or (Get-Field $item 'Subject') -ne 'GutCare 邮箱验证') { continue }
            $messageId = [string](Get-Field $item 'ID')
            if (-not $messageId) { $messageId = [string](Get-Field $item 'Id') }
            if (-not $messageId) { continue }
            $detail = Invoke-Api 'GET' ("$mailpit/api/v1/message/{0}" -f [uri]::EscapeDataString($messageId))
            if ($detail.Status -ne 200) { continue }
            $bodyText = [string](Get-Field $detail.Body 'Text')
            if (-not $bodyText) { $bodyText = [string](Get-Field (Get-Field $detail.Body 'Message') 'Text') }
            $match = [regex]::Match($bodyText, '(?m)^\s*([A-Za-z0-9_-]{60,})\s*$')
            if ($match.Success) { return $match.Groups[1].Value }
        }
        Start-Sleep -Milliseconds 300
    }
    throw 'Mailpit did not provide the synthetic verification message; message contents suppressed.'
}

function Grant-AvailableConsent([string]$Bearer, [string]$ConsentType) {
    $notice = Invoke-Api 'GET' "$api/api/v1/consent-notices?consent_type=$ConsentType" $null $Bearer
    Assert-Status $notice 200 "$ConsentType notice"
    if (-not (Get-Field $notice.Body 'enabled') -or -not (Get-Field $notice.Body 'policy_version')) {
        throw "$ConsentType is disabled in phone-demo configuration."
    }
    $saved = Invoke-Api 'POST' "$api/api/v1/patients/me/consents" @{
        consent_type = $ConsentType
        policy_version = (Get-Field $notice.Body 'policy_version')
        granted = $true
    } $Bearer
    Assert-Status $saved 201 "$ConsentType consent"
}

try {
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw 'Run phone-demo-up.ps1 first.' }
    $health = Invoke-Api 'GET' "$api/health/live"
    Assert-Status $health 200 'phone-demo health'

    $email = "gutcare-f02-$([guid]::NewGuid().ToString('N'))@example.com"
    $password = "Demo-f02-$([guid]::NewGuid().ToString('N'))"
    $registration = Invoke-Api 'POST' "$api/api/v1/auth/register" @{
        email = $email
        password = $password
        birth_year = 1990
        privacy_policy_version = 'test-only-privacy-v1'
        health_data_processing_consent = $true
        health_data_processing_policy_version = 'test-only-health-v1'
    }
    Assert-Status $registration 202 'synthetic registration'
    $verificationToken = Get-MailToken $email
    $verify = Invoke-Api 'POST' "$api/api/v1/auth/email/verify" @{ token = $verificationToken }
    Assert-Status $verify 204 'email verification'
    $login = Invoke-Api 'POST' "$api/api/v1/auth/login" @{ email = $email; password = $password }
    Assert-Status $login 200 'login'
    $accessToken = [string]$login.Body.access_token
    Grant-AvailableConsent $accessToken 'third_party_ai'
    $consents = Invoke-Api 'GET' "$api/api/v1/patients/me/consents" $null $accessToken
    Assert-Status $consents 200 'consent status'
    $healthConsent = @($consents.Body | Where-Object { $_.consent_type -eq 'health_data_processing' -and $_.granted -and $_.policy_version -eq 'test-only-health-v1' })
    if ($healthConsent.Count -ne 1) { throw 'Synthetic account does not have active health-data consent.' }

    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::new(1000, 700)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $font = [System.Drawing.Font]::new('Arial', 30)
    $stream = [System.IO.MemoryStream]::new()
    try {
        $graphics.Clear([System.Drawing.Color]::White)
        $graphics.DrawString("LAB REPORT`nWBC 5.0 10^9/L`nReference range 3.5-9.5 10^9/L", $font, [System.Drawing.Brushes]::Black, 80, 100)
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
        $jpeg = $stream.ToArray()
    } finally { $stream.Dispose(); $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose() }

    $upload = Invoke-Api 'POST' "$api/api/v1/files/uploads" @{
        purpose = 'medical_document'
        file_name = 'synthetic-report.jpg'
        content_type = 'image/jpeg'
        size_bytes = $jpeg.Length
    } $accessToken ("f02-demo-" + [guid]::NewGuid().ToString('N'))
    Assert-Status $upload 201 'upload session'
    $put = Invoke-Api 'PUT' ([string]$upload.Body.upload_url) $jpeg $accessToken
    Assert-Status $put 204 'same-origin file upload'
    $complete = Invoke-Api 'POST' ("$api/api/v1/files/uploads/{0}/complete" -f $upload.Body.upload_id) $null $accessToken
    Assert-Status $complete 200 'upload completion and ClamAV scan'
    $fileId = [string]$complete.Body.id
    if ($complete.Body.storage_status -ne 'available') { throw 'Completed file is not available after scanning.' }

    $document = Invoke-Api 'POST' "$api/api/v1/medical-documents" @{
        file_object_id = $fileId
        document_type = 'other'
        processing_mode = 'analyze'
    } $accessToken
    Assert-Status $document 201 'analyze medical document'
    if ($document.Body.parse_status -notin @('pending', 'processing', 'needs_confirmation', 'succeeded')) {
        throw 'Analyze document did not enter the parse lifecycle.'
    }

    $deadline = (Get-Date).AddSeconds(120)
    $detail = $null
    while ((Get-Date) -lt $deadline) {
        $detail = Invoke-Api 'GET' ("$api/api/v1/medical-documents/{0}" -f $document.Body.id) $null $accessToken
        Assert-Status $detail 200 'medical parse status'
        if ($detail.Body.parse_status -in @('needs_confirmation', 'succeeded', 'failed')) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($null -eq $detail -or $detail.Body.parse_status -notin @('needs_confirmation', 'succeeded')) {
        throw 'Medical parse did not reach a successful terminal state.'
    }

    $candidates = Invoke-Api 'GET' ("$api/api/v1/medical-documents/{0}/candidates" -f $document.Body.id) $null $accessToken
    Assert-Status $candidates 200 'medical field candidates'
    $candidateItems = @($candidates.Body)
    if ($detail.Body.parse_outcome -eq 'extracted') {
        if ($candidateItems.Count -eq 0) { throw 'Extracted outcome did not provide confirmable candidates.' }
        $first = $candidateItems[0]
        $decision = Invoke-Api 'POST' ("$api/api/v1/medical-field-candidates/{0}/decision" -f $first.id) @{
            decision = 'accept'
            record_version = $first.record_version
        } $accessToken ("f02-decision-" + [guid]::NewGuid().ToString('N'))
        Assert-Status $decision 204 'first candidate confirmation'
        $facts = Invoke-Api 'GET' "$api/api/v1/patients/me/confirmed-medical-facts" $null $accessToken
        Assert-Status $facts 200 'confirmed medical facts'
        if (-not @($facts.Body | Where-Object { $_.source_document_id -eq $document.Body.id }).Count) {
            throw 'Confirmed candidate is absent from the patient fact projection.'
        }
    } elseif ($detail.Body.parse_outcome -in @('no_supported_facts', 'insufficient_quality')) {
        if ($candidateItems.Count -ne 0) { throw 'Empty parse outcome unexpectedly returned candidates.' }
    } else {
        throw 'Medical parse completed without a controlled parse outcome.'
    }

    $profile = Invoke-Api 'GET' "$api/api/v1/patients/me" $null $accessToken
    Assert-Status $profile 200 'patient profile'
    $listed = Invoke-Api 'GET' "$api/api/v1/medical-documents?limit=20" $null $accessToken
    Assert-Status $listed 200 'medical archive list'
    if (-not (@($listed.Body.items | Where-Object { $_.id -eq $document.Body.id }).Count)) { throw 'Created store_only document is absent from the archive list.' }
    $detail = Invoke-Api 'GET' ("$api/api/v1/medical-documents/{0}" -f $document.Body.id) $null $accessToken
    Assert-Status $detail 200 'medical archive detail'
    $grant = Invoke-Api 'POST' ("$api/api/v1/files/{0}/download-grants" -f $fileId) $null $accessToken
    Assert-Status $grant 200 'authenticated download grant'
    $download = Invoke-Api 'GET' ([string]$grant.Body.download_url)
    Assert-Status $download 200 'capability download'
    if ($download.Bytes.Length -ne $jpeg.Length -or [Convert]::ToBase64String($download.Bytes) -ne [Convert]::ToBase64String($jpeg)) {
        throw 'Downloaded synthetic bytes do not match the uploaded payload.'
    }

    $fileQuery = @"
from sqlalchemy import create_engine, text
from gutcare.config import get_settings
engine = create_engine(str(get_settings().database_url))
with engine.begin() as connection:
    connection.execute(text("select set_config('app.patient_id', :patient, false)"), {"patient": "$($profile.Body.id)"})
    row = connection.execute(text("select scan_status, storage_status from health.file_object where id=:file_id"), {"file_id": "$fileId"}).one()
    print(f"{row.scan_status},{row.storage_status}")
"@
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw 'Docker CLI is unavailable for scan-state verification.' }
    $composeArgs = @('compose','-f',$composeFile,'--env-file',$envFile,'-p',$project,'exec','-T','api','python','-c',$fileQuery)
    $scanState = (& $docker.Source @composeArgs 2>$null | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0 -or $scanState.Trim() -cne 'clean,available') { throw 'Database scan state is not clean/available; query details suppressed.' }
    Write-Host 'ClamAV/database state clean,available'

    $unauthorized = Invoke-Api 'GET' "$api/api/v1/medical-documents"
    Assert-Status $unauthorized 401 'unauthenticated archive rejection'
    Write-Host ("F02 synthetic analyze dispatch, callback, outcome, archive, and authorized download E2E passed ({0})." -f $detail.Body.parse_outcome)
} finally {
    $client.Dispose()
}
