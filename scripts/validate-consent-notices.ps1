[CmdletBinding()]
param([string]$ContractPath)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    $ContractPath = Join-Path $root 'contracts\consent\consent-notices.json'
}
if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) { throw 'Consent notice artifact is missing.' }
$bytes = [System.IO.File]::ReadAllBytes($ContractPath)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { throw 'Consent notice artifact must be UTF-8 without BOM.' }
if ([Array]::IndexOf($bytes, [byte]0x0D) -ge 0) { throw 'Consent notice artifact must use LF line endings.' }
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$artifact = $utf8.GetString($bytes) | ConvertFrom-Json
if ($artifact.schema_version -ne '1.0' -or $artifact.artifact_classification -ne 'development_test_only' -or $artifact.legal_approval_status -ne 'not_approved_for_production') {
    throw 'Repository consent notice artifact must be explicitly development/test only and not production approved.'
}
$expected = @('health_data_processing', 'mood_data_processing', 'mood_ai_sharing', 'third_party_ai')
if (@($artifact.notices).Count -ne $expected.Count) { throw 'Consent notice artifact must contain exactly the four supported consent notices.' }
$mapping = @{
    health_data_processing = @('HEALTH_DATA_PROCESSING_POLICY_VERSION', 'HEALTH_DATA_PROCESSING_SUMMARY_HASH')
    mood_data_processing = @('MOOD_DATA_PROCESSING_POLICY_VERSION', 'MOOD_DATA_PROCESSING_SUMMARY_HASH')
    mood_ai_sharing = @('MOOD_AI_SHARING_POLICY_VERSION', 'MOOD_AI_SHARING_SUMMARY_HASH')
    third_party_ai = @('THIRD_PARTY_AI_POLICY_VERSION', 'THIRD_PARTY_AI_SUMMARY_HASH')
}
$expectedConfig = @{}
foreach ($type in $expected) {
    $matches = @($artifact.notices | Where-Object { $_.consent_type -eq $type })
    if ($matches.Count -ne 1) { throw "Consent notice artifact must contain exactly one $type notice." }
    $notice = $matches[0]
    foreach ($field in @('policy_version', 'summary', 'purpose', 'data_scope', 'recipient', 'withdrawal_effect')) {
        if ([string]::IsNullOrWhiteSpace([string]$notice.$field)) { throw "$type notice field $field must not be empty." }
    }
    if ($notice.enabled -ne $true -or -not ([string]$notice.policy_version).StartsWith('test-only-', [StringComparison]::Ordinal)) { throw "$type must be enabled only under a test-only version." }
    $normalized = ([string]$notice.summary).Replace("`r`n", "`n").Replace("`r", "`n")
    $digest = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.Text.UTF8Encoding]::new($false).GetBytes($normalized))).ToLowerInvariant()
    if ($digest -cne [string]$notice.summary_sha256) { throw "$type summary hash does not match its canonical UTF-8/LF text." }
    $expectedConfig[$mapping[$type][0]] = [string]$notice.policy_version
    $expectedConfig[$mapping[$type][1]] = $digest
}
$actualKeys = @($artifact.backend_config.PSObject.Properties.Name | Sort-Object)
$expectedKeys = @($expectedConfig.Keys | Sort-Object)
if (($actualKeys -join "`n") -cne ($expectedKeys -join "`n")) { throw 'Consent notice backend_config key set differs from the supported notices.' }
foreach ($key in $expectedKeys) { if ([string]$artifact.backend_config.$key -cne [string]$expectedConfig[$key]) { throw "Backend config $key does not match its consent notice." } }
$envPath = Join-Path $root '.env.example'
$envValues = @{}
foreach ($line in [System.IO.File]::ReadAllLines($envPath, $utf8)) { if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') { $envValues[$Matches[1]] = $Matches[2] } }
foreach ($key in $expectedKeys) { if (-not $envValues.ContainsKey($key) -or [string]$envValues[$key] -cne [string]$expectedConfig[$key]) { throw ".env.example setting $key does not match the test artifact." } }
Write-Host 'Consent notice artifact hashes, test-only classification and backend settings are consistent.'
