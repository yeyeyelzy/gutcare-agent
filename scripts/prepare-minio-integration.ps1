[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$toolchainRoot = Join-Path $root '.runtime\go-1.24.8'
$toolchainZip = Join-Path $root '.downloads\go1.24.8.windows-amd64.zip'
$toolchainExtract = Join-Path $root '.runtime\go-extract-1.24.8'
$runtimeGo = Join-Path $toolchainRoot 'go\bin\go.exe'
$goPath = Join-Path $root '.runtime\go-gopath'
$minioArtifact = Join-Path $root '.downloads\minio'
$context = Join-Path $root '.downloads\minio-context'
$phoneDemoInitContext = Join-Path $root '.downloads\phone-demo-minio-init-context'
$moduleVersion = 'RELEASE.2025-09-07T16-13-09Z'
$mcModuleVersion = 'v0.0.0-20250313080218-cf909e1063a9'

New-Item -ItemType Directory -Path (Split-Path -Parent $toolchainZip) -Force | Out-Null
New-Item -ItemType Directory -Path $minioArtifact -Force | Out-Null

if (-not (Test-Path -LiteralPath $runtimeGo -PathType Leaf)) {
    $releaseIndex = Invoke-RestMethod -Uri 'https://go.dev/dl/?mode=json&include=all'
    $release = $releaseIndex | Where-Object { $_.version -eq 'go1.24.8' } | Select-Object -First 1
    $archive = $release.files | Where-Object { $_.filename -eq 'go1.24.8.windows-amd64.zip' } | Select-Object -First 1
    if (-not $archive -or -not $archive.sha256) {
        throw 'The official Go download index did not provide the pinned Windows archive and SHA-256.'
    }
    if (-not (Test-Path -LiteralPath $toolchainZip -PathType Leaf)) {
        Invoke-WebRequest -Uri "https://go.dev/dl/$($archive.filename)" -OutFile $toolchainZip
    }
    $actualHash = (Get-FileHash -LiteralPath $toolchainZip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $archive.sha256.ToLowerInvariant()) {
        throw "Go toolchain SHA-256 mismatch: expected $($archive.sha256), got $actualHash."
    }
    if (Test-Path -LiteralPath $toolchainExtract) {
        if (-not (Test-Path -LiteralPath (Join-Path $toolchainExtract 'go\bin\go.exe') -PathType Leaf)) {
            throw "Refusing to overwrite unrecognized extraction path: $toolchainExtract"
        }
    } else {
        Expand-Archive -LiteralPath $toolchainZip -DestinationPath $toolchainExtract
    }
    New-Item -ItemType Directory -Path $toolchainRoot -Force | Out-Null
    Move-Item -LiteralPath (Join-Path $toolchainExtract 'go') -Destination (Join-Path $toolchainRoot 'go')
}

$goVersion = & $runtimeGo version
if ($LASTEXITCODE -ne 0 -or $goVersion -notmatch '^go version go1\.24\.8 windows/amd64') {
    throw "Pinned Go toolchain is invalid: $goVersion"
}

$env:GOOS = 'linux'
$env:GOARCH = 'amd64'
$env:CGO_ENABLED = '0'
$env:GOPATH = $goPath
$env:GOMODCACHE = Join-Path $root '.runtime\gomodcache'
$env:GOCACHE = Join-Path $root '.runtime\gocache'
$env:GOTOOLCHAIN = 'local'
New-Item -ItemType Directory -Path $env:GOPATH, $env:GOMODCACHE, $env:GOCACHE -Force | Out-Null

$minioBinary = Join-Path $env:GOPATH 'bin\linux_amd64\minio'
if (-not (Test-Path -LiteralPath $minioBinary -PathType Leaf)) {
    & $runtimeGo install "github.com/minio/minio@$moduleVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Official MinIO source build failed for $moduleVersion (exit $LASTEXITCODE)."
    }
}

$mcBinary = Join-Path $env:GOPATH 'bin\linux_amd64\mc'
if (-not (Test-Path -LiteralPath $mcBinary -PathType Leaf)) {
    & $runtimeGo install "github.com/minio/mc@$mcModuleVersion"
    if ($LASTEXITCODE -ne 0) {
        throw "Pinned MinIO Client source build failed for $mcModuleVersion (exit $LASTEXITCODE)."
    }
}

Copy-Item -LiteralPath $minioBinary -Destination (Join-Path $minioArtifact 'minio') -Force
$binaryHash = (Get-FileHash -LiteralPath (Join-Path $minioArtifact 'minio') -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $minioArtifact 'minio.sha256') -Value $binaryHash -NoNewline -Encoding ascii

New-Item -ItemType Directory -Path $context -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\infra\minio\Dockerfile.integration') -Destination (Join-Path $context 'Dockerfile') -Force
Copy-Item -LiteralPath (Join-Path $minioArtifact 'minio') -Destination (Join-Path $context 'minio') -Force
Copy-Item -LiteralPath $mcBinary -Destination (Join-Path $context 'mc') -Force
New-Item -ItemType Directory -Path $phoneDemoInitContext -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\infra\minio\Dockerfile.phone-demo-init') -Destination (Join-Path $phoneDemoInitContext 'Dockerfile') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\infra\minio\phone-demo-minio-init.py') -Destination $phoneDemoInitContext -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot '..\infra\minio\phone-demo-app-policy.json') -Destination $phoneDemoInitContext -Force
Copy-Item -LiteralPath $mcBinary -Destination (Join-Path $phoneDemoInitContext 'mc') -Force
Write-Host "Prepared official MinIO $moduleVersion Linux/amd64 binary (SHA-256 $binaryHash)."
