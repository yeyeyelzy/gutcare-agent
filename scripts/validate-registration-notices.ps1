[CmdletBinding()]
param(
    [string]$ContractPath,
    [string]$EnvExamplePath
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($ContractPath)) {
    $ContractPath = Join-Path $root 'contracts\consent\registration-notices.json'
}
if ([string]::IsNullOrWhiteSpace($EnvExamplePath)) {
    $EnvExamplePath = Join-Path $root '.env.example'
}

if (-not (Test-Path -LiteralPath $ContractPath -PathType Leaf)) {
    throw 'Registration notice contract is missing.'
}
if (-not (Test-Path -LiteralPath $EnvExamplePath -PathType Leaf)) {
    throw 'Backend environment example is missing.'
}

$bytes = [System.IO.File]::ReadAllBytes($ContractPath)
if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    throw 'Registration notice contract must be UTF-8 without BOM.'
}
if ([Array]::IndexOf($bytes, [byte]0x0D) -ge 0) {
    throw 'Registration notice contract must use LF line endings.'
}

$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
try {
    $jsonText = $utf8.GetString($bytes)
} catch {
    throw 'Registration notice contract must contain valid UTF-8.'
}
$contract = $jsonText | ConvertFrom-Json

if ($contract.schema_version -ne '1.0') {
    throw 'Unsupported registration notice contract schema_version.'
}
if ($contract.artifact_classification -ne 'development_test_only' -or
    $contract.legal_approval_status -ne 'not_approved_for_production') {
    throw 'The repository registration notice artifact must be explicitly development/test only.'
}

$expectedTypes = @('privacy_policy', 'health_data_processing')
$notices = @($contract.notices)
if ($notices.Count -ne $expectedTypes.Count) {
    throw 'Registration notice contract must contain exactly two notices.'
}

$expectedConfig = @{}
foreach ($consentType in $expectedTypes) {
    $matches = @($notices | Where-Object { $_.consent_type -eq $consentType })
    if ($matches.Count -ne 1) {
        throw "Registration notice contract must contain exactly one $consentType notice."
    }
    $notice = $matches[0]
    if ([string]::IsNullOrWhiteSpace([string]$notice.policy_version) -or
        -not ([string]$notice.policy_version).StartsWith('test-only-', [StringComparison]::Ordinal)) {
        throw "$consentType must use an explicitly test-only policy version."
    }
    if (([string]$notice.policy_version).Length -gt 32) {
        throw "$consentType policy version exceeds the frozen API maximum of 32 characters."
    }
    if ([string]::IsNullOrWhiteSpace([string]$notice.summary)) {
        throw "$consentType summary must not be empty."
    }
    $normalizedSummary = ([string]$notice.summary).Replace("`r`n", "`n").Replace("`r", "`n")
    $summaryBytes = [System.Text.UTF8Encoding]::new($false).GetBytes($normalizedSummary)
    $digestBytes = [System.Security.Cryptography.SHA256]::Create().ComputeHash($summaryBytes)
    $digest = ([BitConverter]::ToString($digestBytes)).Replace('-', '').ToLowerInvariant()
    if ($digest -cne [string]$notice.summary_sha256) {
        throw "$consentType summary SHA-256 does not match its UTF-8/LF content."
    }

    if ($consentType -eq 'privacy_policy') {
        $expectedConfig['PRIVACY_POLICY_VERSION'] = [string]$notice.policy_version
        $expectedConfig['PRIVACY_POLICY_SUMMARY_HASH'] = $digest
    } else {
        $expectedConfig['HEALTH_DATA_PROCESSING_POLICY_VERSION'] = [string]$notice.policy_version
        $expectedConfig['HEALTH_DATA_PROCESSING_SUMMARY_HASH'] = $digest
    }
}

$actualConfigProperties = @($contract.backend_config.PSObject.Properties.Name | Sort-Object)
$expectedConfigProperties = @($expectedConfig.Keys | Sort-Object)
if (($actualConfigProperties -join "`n") -cne ($expectedConfigProperties -join "`n")) {
    throw 'Registration notice backend_config must contain exactly the four frozen settings.'
}
foreach ($name in $expectedConfigProperties) {
    if ([string]$contract.backend_config.$name -cne [string]$expectedConfig[$name]) {
        throw "Registration notice backend setting $name does not match its notice."
    }
}

$envExample = @{}
foreach ($line in [System.IO.File]::ReadAllLines($EnvExamplePath, $utf8)) {
    if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
        if ($envExample.ContainsKey($Matches[1])) {
            throw ".env.example contains duplicate setting $($Matches[1])."
        }
        $envExample[$Matches[1]] = $Matches[2]
    }
}
foreach ($name in $expectedConfigProperties) {
    if (-not $envExample.ContainsKey($name) -or
        [string]$envExample[$name] -cne [string]$expectedConfig[$name]) {
        throw ".env.example setting $name must match the development/test notice artifact."
    }
}

Write-Host 'Registration notice UTF-8/LF hashes and four backend settings are consistent.'
