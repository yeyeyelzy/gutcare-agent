[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'SHA256SUMS.txt') -PathType Leaf) {
    $PSScriptRoot
} else {
    Split-Path -Parent $PSScriptRoot
}
$manifestPath = Join-Path $root 'SHA256SUMS.txt'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw 'Package hash manifest SHA256SUMS.txt is missing.'
}

$rootPrefix = [System.IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
$checked = 0
$failures = [System.Collections.Generic.List[string]]::new()
# Windows PowerShell 5.1 defaults to the active ANSI code page for BOM-less
# files.  The manifest is UTF-8 and contains Chinese path names, so decoding it
# explicitly avoids corrupted (and sometimes invalid) Windows paths.
foreach ($line in Get-Content -LiteralPath $manifestPath -Encoding UTF8) {
    if ($line -notmatch '^([0-9a-fA-F]{64})  (.+)$') {
        $failures.Add('Malformed line in SHA256SUMS.txt.')
        continue
    }
    $expectedHash = $Matches[1].ToLowerInvariant()
    $relativePath = $Matches[2].Replace('/', '\')
    $fullPath = [System.IO.Path]::GetFullPath((Join-Path $root $relativePath))
    if (-not $fullPath.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        $failures.Add('Manifest path escapes the package directory.')
        continue
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        $failures.Add("Missing package file: $relativePath")
        continue
    }
    $actualHash = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        $failures.Add("Hash mismatch: $relativePath")
        continue
    }
    $checked++
}

foreach ($relativePath in @('compose.phone-demo.yaml', 'android\app-debug.apk', 'Start-GutCareDemo.ps1', 'Stop-GutCareDemo.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relativePath) -PathType Leaf)) {
        $failures.Add("Required package file is missing: $relativePath")
    }
}
if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    throw 'Package verification failed.'
}
Write-Host "Package verification passed: $checked SHA-256 entries; required startup files are present."
