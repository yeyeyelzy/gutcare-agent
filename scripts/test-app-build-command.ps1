[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'app-build-command.ps1')
$cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'

Invoke-AppBuildCommand -FilePath $cmd -TargetName 'stderr-success' -ArgumentList @(
    '/d', '/c', 'echo warning-stderr-visible-success 1>&2 & exit /b 0'
)

$nonzeroFailed = $false
try {
    Invoke-AppBuildCommand -FilePath $cmd -TargetName 'stderr-nonzero' -ArgumentList @(
        '/d', '/c', 'echo failure-stderr-visible 1>&2 & exit /b 7'
    )
} catch {
    $nonzeroFailed = $_.Exception.Message -match 'exit=7'
}

if (-not $nonzeroFailed) {
    throw 'A native command with visible stderr and exit code 7 was not rejected.'
}

Write-Output 'Native APP build command stderr/exit-code contract: PASS'
