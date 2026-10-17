[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $node) { throw 'Project Node resolver did not return an executable.' }
& (Join-Path $PSScriptRoot 'lint.ps1')
if (-not $?) { throw 'Lint failed.' }
& (Join-Path $PSScriptRoot 'test.ps1') -Suite unit
if (-not $?) { throw 'Unit test suite failed.' }
$originalApiBaseUrl = $env:VITE_API_BASE_URL
try {
    if ([string]::IsNullOrWhiteSpace($env:VITE_API_BASE_URL)) {
        $env:VITE_API_BASE_URL = 'https://api.gutcare.test/api/v1'
    }
    & (Join-Path $PSScriptRoot 'app-build.ps1')
    if (-not $?) { throw 'APP Android/iOS builds failed.' }
} finally {
    $env:VITE_API_BASE_URL = $originalApiBaseUrl
}
