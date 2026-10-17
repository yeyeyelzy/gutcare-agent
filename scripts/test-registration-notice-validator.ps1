[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$validator = Join-Path $PSScriptRoot 'validate-registration-notices.ps1'
$contract = Join-Path $root 'contracts\consent\registration-notices.json'
$sourceEnv = Join-Path $root '.env.example'
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) (
    'gutcare-registration-notice-validator-' + [Guid]::NewGuid().ToString('N')
)
$temporaryEnv = Join-Path $temporaryDirectory '.env.example'

[void][System.IO.Directory]::CreateDirectory($temporaryDirectory)
try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    $sourceText = [System.IO.File]::ReadAllText($sourceEnv, $utf8)
    $duplicateText = $sourceText.TrimEnd("`r`n".ToCharArray()) +
        "`nPRIVACY_POLICY_VERSION=duplicate-must-fail`n"
    [System.IO.File]::WriteAllText($temporaryEnv, $duplicateText, $utf8)

    $failedAsExpected = $false
    try {
        & $validator -ContractPath $contract -EnvExamplePath $temporaryEnv
    } catch {
        if ($_.Exception.Message -notmatch 'duplicate setting PRIVACY_POLICY_VERSION') {
            throw
        }
        $failedAsExpected = $true
    }
    if (-not $failedAsExpected) {
        throw 'Registration notice validator accepted a duplicate .env.example key.'
    }
} finally {
    if (Test-Path -LiteralPath $temporaryEnv -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryEnv -Force
    }
    if (Test-Path -LiteralPath $temporaryDirectory -PathType Container) {
        Remove-Item -LiteralPath $temporaryDirectory -Force
    }
}

Write-Host 'Registration notice validator duplicate-key rejection passed.'
