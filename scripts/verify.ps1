[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'resolve-python.ps1')
if (-not $python) { throw 'Project Python resolver did not return an executable.' }
& (Join-Path $PSScriptRoot 'lint.ps1')
if (-not $?) { throw 'Lint failed.' }
& (Join-Path $PSScriptRoot 'test.ps1') -Suite unit
if (-not $?) { throw 'Unit test suite failed.' }
