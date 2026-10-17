param(
    [switch] $ValidateOnly,
    [string] $SourceZip
)

$ErrorActionPreference = 'Stop'
$expectedZipHash = '8f6667b23a0edd865f97ed682fa4e873a4f38a94fc615d569292abcc7b5ca695'
$appRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $appRoot '..')).Path
$assetsDir = Join-Path $repoRoot 'design-reference/ui-prototype-assets'
$manifestPath = Join-Path $assetsDir 'asset-manifest.json'
$assetSpec = @(
    [ordered]@{ file = 'avatar-profile-prototype.png'; sha256 = 'ccbd00c88bf433fe243286242fc046e2b4383947b34ef67eced5adb00c0b27c6'; width = 140; height = 142; type = 'png' }
    [ordered]@{ file = 'meal-lunch-prototype.png'; sha256 = 'b937965dd68dc9f61dc25420522024bd8c8bf2a5327895ff7b18cc2e8f0eeb70'; width = 270; height = 217; type = 'png' }
    [ordered]@{ file = 'meal-dinner-illustration.svg'; sha256 = '2b5d7926fd7957c2b884fd5a1ac2c89aa62b7a35d424c43ab54d53054562fce3'; width = 600; height = 360; type = 'svg+xml' }
    [ordered]@{ file = 'meal-recognition-pork.png'; sha256 = 'f5b6098c903805e3701b45605d435fcfc985806d9476d21d1f3dc07183448736'; width = 90; height = 68; type = 'png' }
    [ordered]@{ file = 'meal-recognition-rice.png'; sha256 = '1303c639badda5f4055a74d1f8968865d063c51a01a7cb3a1c4487f27dd88a38'; width = 90; height = 69; type = 'png' }
    [ordered]@{ file = 'meal-recognition-vegetable.png'; sha256 = '9a5bc0f29947677284dca632725d3b33b07640840321821e560f76f606cbaa03'; width = 90; height = 67; type = 'png' }
)
$assetsByHash = @{}
foreach ($spec in $assetSpec) { $assetsByHash[$spec.sha256] = $spec }

function Get-BytesHash([byte[]] $Bytes) {
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}

function Get-PngDimensions([byte[]] $Bytes) {
    $signature = [byte[]](137, 80, 78, 71, 13, 10, 26, 10)
    if ($Bytes.Length -lt 24) { throw 'PNG is shorter than its signature and IHDR.' }
    for ($i = 0; $i -lt $signature.Length; $i++) {
        if ($Bytes[$i] -ne $signature[$i]) { throw 'PNG signature is invalid.' }
    }
    return [ordered]@{
        width = [int]($Bytes[16] * 16777216 + $Bytes[17] * 65536 + $Bytes[18] * 256 + $Bytes[19])
        height = [int]($Bytes[20] * 16777216 + $Bytes[21] * 65536 + $Bytes[22] * 256 + $Bytes[23])
    }
}

function Get-SvgDimensions([byte[]] $Bytes) {
    $svgText = [Text.Encoding]::UTF8.GetString($Bytes)
    if ($svgText -match '(?is)<!\s*(DOCTYPE|ENTITY)') { throw 'SVG DTD and ENTITY declarations are forbidden.' }
    $settings = [Xml.XmlReaderSettings]::new()
    $settings.DtdProcessing = [Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $stringReader = [IO.StringReader]::new($svgText)
    $reader = [Xml.XmlReader]::Create($stringReader, $settings)
    $document = [Xml.XmlDocument]::new()
    $document.XmlResolver = $null
    try { $document.Load($reader) } finally { $reader.Dispose(); $stringReader.Dispose() }
    $root = $document.DocumentElement
    if ($null -eq $root -or $root.LocalName -ne 'svg') { throw 'SVG root element is missing.' }
    foreach ($element in $document.SelectNodes('//*')) {
        if ($element.LocalName -match '^(?i:script|foreignObject|style)$') { throw "Forbidden SVG element: $($element.LocalName)" }
        foreach ($attribute in $element.Attributes) {
            $name = $attribute.LocalName.ToLowerInvariant()
            $value = $attribute.Value
            if ($name -match '^on[a-z]+$') { throw "SVG event handler attribute is forbidden: $name" }
            if ($name -eq 'style' -or $value -match '(?i)@import|url\s*\(') { throw 'SVG CSS and URL references are forbidden.' }
            if ($name -eq 'href' -and !$value.StartsWith('#')) { throw 'SVG external href is forbidden.' }
            if ($attribute.Prefix -ne 'xmlns' -and $name -ne 'xmlns' -and $value -match '(?i)(https?:)?//') { throw 'SVG external URL values are forbidden.' }
        }
    }
    if ($svgText -match '(?i)@import|url\s*\(') { throw 'SVG CSS imports and url() references are forbidden.' }
    $width = [regex]::Match($root.GetAttribute('width'), '^[0-9]+$')
    $height = [regex]::Match($root.GetAttribute('height'), '^[0-9]+$')
    if (!$width.Success -or !$height.Success) { throw 'SVG must declare integer width and height.' }
    return [ordered]@{ width = [int]$width.Value; height = [int]$height.Value }
}

function Get-AssetInfo([string] $Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $extension = [IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($extension -eq '.png') { $dimensions = Get-PngDimensions $bytes }
    elseif ($extension -eq '.svg') { $dimensions = Get-SvgDimensions $bytes }
    else { throw "Unexpected prototype asset type: $extension" }
    return [ordered]@{
        file = [IO.Path]::GetFileName($Path)
        width = $dimensions.width
        height = $dimensions.height
        size_bytes = $bytes.Length
        sha256 = Get-BytesHash $bytes
    }
}

function Test-IsExcludedPath([string] $CandidatePath, [string[]] $Directories, [string[]] $Files) {
    $candidate = [IO.Path]::GetFullPath($CandidatePath)
    foreach ($file in $Files) {
        if ([string]::Equals($candidate, [IO.Path]::GetFullPath($file), [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($directory in $Directories) {
        $root = [IO.Path]::GetFullPath($directory).TrimEnd([char[]]@('\', '/'))
        if ([string]::Equals($candidate, $root, [StringComparison]::OrdinalIgnoreCase)) { return $true }
        $windowsPrefix = $root + '\'
        $portablePrefix = $root + '/'
        if ($candidate.StartsWith($windowsPrefix, [StringComparison]::OrdinalIgnoreCase) -or
            $candidate.StartsWith($portablePrefix, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Assert-BuildInputsAndArtifactsClean {
    $skipDirectories = @(
        (Join-Path $appRoot 'node_modules'),
        (Join-Path $repoRoot 'docs'),
        (Join-Path $repoRoot 'design-reference')
    )
    $skipFiles = @((Join-Path $appRoot 'scripts/freeze-ui-assets.ps1'))
    $scanFiles = @(
        Get-ChildItem $appRoot -Recurse -File | Where-Object {
            -not (Test-IsExcludedPath $_.FullName $skipDirectories $skipFiles)
        }
    )
    foreach ($folder in @((Join-Path $repoRoot '.github/workflows'), (Join-Path $repoRoot 'scripts'))) {
        if (Test-Path $folder) {
            $scanFiles += Get-ChildItem $folder -Recurse -File | Where-Object {
                -not (Test-IsExcludedPath $_.FullName $skipDirectories $skipFiles)
            }
        }
    }
    foreach ($fileName in @('package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml')) {
        $path = Join-Path $repoRoot $fileName
        if (Test-Path -LiteralPath $path -PathType Leaf) { $scanFiles += Get-Item -LiteralPath $path }
    }
    $blockedTextTokens = @('ui-prototype-assets')
    $designReferencePathPattern = '(?i)(?<![\w.-])design-reference(?=$|[\\/]|[*?{])'
    foreach ($spec in $assetSpec) { $blockedTextTokens += $spec.file; $blockedTextTokens += $spec.sha256 }
    $payloads = @(
        foreach ($spec in $assetSpec) {
            $bytes = [IO.File]::ReadAllBytes((Join-Path $assetsDir $spec.file))
            [Convert]::ToBase64String($bytes)
        }
    )
    foreach ($file in $scanFiles) {
        $bytes = [IO.File]::ReadAllBytes($file.FullName)
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        if ($text -match $designReferencePathPattern) {
            throw "Build input/config/artifact references the quarantined design-reference path: $($file.FullName)"
        }
        foreach ($token in $blockedTextTokens) {
            if ($text.IndexOf($token, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                throw "Build input/config/artifact references quarantined prototype data ($token): $($file.FullName)"
            }
        }
        foreach ($payload in $payloads) {
            if ($text.Contains($payload)) { throw "Build input/config/artifact contains a quarantined image payload: $($file.FullName)" }
        }
        foreach ($spec in $assetSpec) {
            if ((Get-BytesHash $bytes) -eq $spec.sha256) { throw "Build artifact is an unapproved prototype asset: $($file.FullName)" }
        }
    }
}

function Assert-Manifest($Manifest) {
    $manifestBytes = [IO.File]::ReadAllBytes($manifestPath)
    if ($manifestBytes.Length -lt 4 -or
        ($manifestBytes[0] -eq 0xEF -and $manifestBytes[1] -eq 0xBB -and $manifestBytes[2] -eq 0xBF)) {
        throw 'Manifest must be UTF-8 without BOM.'
    }
    $manifestText = [Text.UTF8Encoding]::new($false, $true).GetString($manifestBytes)
    if ($manifestText.Contains("`r") -or !$manifestText.EndsWith("`n") -or $manifestText.EndsWith("`n`n")) {
        throw 'Manifest must use LF line endings and end in exactly one LF.'
    }
    if ($Manifest.source_zip_sha256 -ne $expectedZipHash) { throw 'Manifest source ZIP SHA-256 mismatch.' }
    if ($Manifest.asset_count -ne $assetSpec.Count -or $Manifest.assets.Count -ne $assetSpec.Count) { throw 'Manifest asset_count/list size mismatch.' }
    if ($Manifest.license_status -ne 'user_provided_provenance_unconfirmed' -or $Manifest.production_allowed -ne $false) {
        throw 'Manifest must block production until provenance is confirmed.'
    }
    $expectedFiles = @($assetSpec | ForEach-Object { $_.file } | Sort-Object)
    $directoryEntries = @(Get-ChildItem -LiteralPath $assetsDir -Force | ForEach-Object { $_.Name } | Sort-Object)
    $allowedEntries = @($expectedFiles + 'asset-manifest.json' | Sort-Object)
    if (Compare-Object $allowedEntries $directoryEntries) { throw 'Prototype reference directory contains missing or unexpected entries.' }

    $manifestFiles = @($Manifest.assets | ForEach-Object { $_.file })
    if (($manifestFiles | Sort-Object -Unique).Count -ne $assetSpec.Count) { throw 'Manifest filenames are not unique.' }
    $manifestHashes = @($Manifest.assets | ForEach-Object { $_.sha256 })
    if (($manifestHashes | Sort-Object -Unique).Count -ne $assetSpec.Count) { throw 'Manifest asset hashes are not unique.' }
    foreach ($spec in $assetSpec) {
        $records = @($Manifest.assets | Where-Object { $_.file -eq $spec.file })
        if ($records.Count -ne 1) { throw "Manifest must contain exactly one record for $($spec.file)." }
        $record = $records[0]
        $path = Join-Path $assetsDir $spec.file
        $actual = Get-AssetInfo $path
        if ($actual.sha256 -ne $spec.sha256 -or $record.sha256 -ne $spec.sha256) { throw "Pinned asset hash mismatch: $($spec.file)" }
        if ($actual.width -ne $spec.width -or $actual.height -ne $spec.height -or $record.width -ne $spec.width -or $record.height -ne $spec.height) {
            throw "Pinned asset dimensions mismatch: $($spec.file)"
        }
        if ($record.size_bytes -ne $actual.size_bytes -or $record.license_status -ne 'user_provided_provenance_unconfirmed' -or $record.production_allowed -ne $false) {
            throw "Manifest metadata mismatch: $($spec.file)"
        }
    }
}

if ($ValidateOnly) {
    if (!(Test-Path -LiteralPath $manifestPath)) { throw "Missing manifest: $manifestPath" }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Assert-Manifest $manifest
    Assert-BuildInputsAndArtifactsClean
    Write-Output 'Prototype assets, fixed allowlist, manifest, dimensions, SVG XML safety, build inputs, and production artifacts: PASS'
    exit 0
}

if ([string]::IsNullOrWhiteSpace($SourceZip)) { throw 'Extraction requires -SourceZip <zip-file-path>.' }
if (!(Test-Path -LiteralPath $SourceZip -PathType Leaf)) { throw 'Source ZIP does not exist.' }
$actualZipHash = (Get-FileHash -LiteralPath $SourceZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualZipHash -ne $expectedZipHash) { throw "Source ZIP hash mismatch: $actualZipHash" }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($SourceZip)
try {
    $entry = $archive.GetEntry('app.js')
    if ($null -eq $entry) { throw 'Expected app.js source entry is missing.' }
    $reader = [IO.StreamReader]::new($entry.Open())
    try { $javascript = $reader.ReadToEnd() } finally { $reader.Dispose() }
} finally { $archive.Dispose() }

$matches = [regex]::Matches($javascript, 'data:image/(png|svg\+xml);base64,([A-Za-z0-9+/=]+)')
$extracted = @{}
foreach ($match in $matches) {
    $bytes = [Convert]::FromBase64String($match.Groups[2].Value)
    $hash = Get-BytesHash $bytes
    if (!$assetsByHash.ContainsKey($hash)) { throw "Unrecognized image payload in source: $hash" }
    if ($extracted.ContainsKey($hash)) { continue }
    $spec = $assetsByHash[$hash]
    if ($match.Groups[1].Value -ne $spec.type) { throw "MIME mismatch for $($spec.file)." }
    if (!(Test-Path -LiteralPath $assetsDir)) { New-Item -ItemType Directory -Path $assetsDir -Force | Out-Null }
    $path = Join-Path $assetsDir $spec.file
    if ((Test-Path -LiteralPath $path) -and (Get-BytesHash ([IO.File]::ReadAllBytes($path))) -ne $spec.sha256) {
        throw "Refusing to overwrite changed reference asset: $($spec.file)"
    }
    [IO.File]::WriteAllBytes($path, $bytes)
    $assetInfo = Get-AssetInfo $path
    if ($assetInfo.sha256 -ne $spec.sha256 -or $assetInfo.width -ne $spec.width -or $assetInfo.height -ne $spec.height) {
        throw "Extracted asset does not match the frozen allowlist: $($spec.file)"
    }
    $extracted[$hash] = $assetInfo
}
if ($extracted.Count -ne $assetSpec.Count) { throw "Expected six unique image assets, found $($extracted.Count)." }

$assetRecords = @(
    foreach ($spec in $assetSpec) {
        $info = $extracted[$spec.sha256]
        [ordered]@{
            file = $info.file
            width = $info.width
            height = $info.height
            size_bytes = $info.size_bytes
            sha256 = $info.sha256
            license_status = 'user_provided_provenance_unconfirmed'
            production_allowed = $false
        }
    }
)
$manifest = [ordered]@{
    source_zip = [IO.Path]::GetFileName($SourceZip)
    source_zip_sha256 = $actualZipHash
    asset_count = $assetRecords.Count
    license_status = 'user_provided_provenance_unconfirmed'
    production_allowed = $false
    assets = $assetRecords
}
# Normalize ConvertTo-Json host newlines before writing stable UTF-8/LF bytes.
$manifestJson = ($manifest | ConvertTo-Json -Depth 6) -replace '\r\n|\r|\n', "`n"
$manifestJson = $manifestJson.TrimEnd([char[]]@("`r", "`n"))
$manifestBytes = [Text.UTF8Encoding]::new($false).GetBytes($manifestJson + "`n")
[IO.File]::WriteAllBytes($manifestPath, $manifestBytes)
Assert-Manifest $manifest
Assert-BuildInputsAndArtifactsClean
Write-Output "Extracted and validated $($assetRecords.Count) unique static image assets from the hash-pinned archive."
