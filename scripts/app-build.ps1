[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$node = & (Join-Path $PSScriptRoot 'resolve-node.ps1')
if (-not $node) { throw 'Project Node resolver did not return an executable.' }

$packageManager = (Get-Content -LiteralPath (Join-Path $root 'app\package.json') -Raw | ConvertFrom-Json).packageManager
if ($packageManager -ne 'pnpm@10.28.0') { throw 'APP requires the package manager pinned in app/package.json.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'pnpm-lock.yaml') -PathType Leaf)) { throw 'Workspace pnpm-lock.yaml is missing.' }
if (-not $env:VITE_API_BASE_URL) { throw 'Set VITE_API_BASE_URL before building the APP.' }

$corepack = Join-Path (Split-Path -Parent $node) 'node_modules\corepack\dist\corepack.js'
if (-not (Test-Path -LiteralPath $corepack -PathType Leaf)) { throw 'Project Node 22 Corepack runtime is missing.' }
$env:COREPACK_HOME = Join-Path $root '.runtime\corepack'
$appPath = Join-Path $root 'app'
Push-Location $appPath
try {
    $version = & $node $corepack pnpm --version
    if ($LASTEXITCODE -ne 0 -or $version -ne '10.28.0') { throw "pnpm 10.28.0 is required; resolver reports '$version'." }
    foreach ($target in @(
        @{ Name = 'Android'; Script = 'build:android'; Artifact = 'dist\build\hx\app\app-android\uni_modules\gutcare-secure-store\manifest.json'; CompilerArtifact = 'dist\build\.tsc\uni_modules\gutcare-secure-store\utssdk\app-android\index.uts.ts' },
        @{ Name = 'iOS'; Script = 'build:ios'; Artifact = 'dist\build\hx\app\app-ios\uni_modules\gutcare-secure-store\manifest.json'; CompilerArtifact = 'dist\build\.tsc\uni_modules\gutcare-secure-store\utssdk\app-ios\index.uts.ts' }
    )) {
        $buildStartedAt = Get-Date
        $output = & $node $corepack pnpm run $target.Script 2>&1
        $exitCode = $LASTEXITCODE
        $output | ForEach-Object { Write-Output $_ }
        $text = ($output | ForEach-Object { [string]$_ }) -join "`n"

        $diagnostics = @(
            '(?im)^\s*x\s+',
            '(?i)Cannot find module:',
            '(?i)Module not found',
            '(?i)UTS.{0,40}(error|failed|exception)',
            '(?i)(Syntax|Compile|Compilation) Error',
            '(?i)Build failed',
            '(?i)error TS\d+',
            '(?i)Error:'
        )
        $diagnostic = $diagnostics | Where-Object { $text -match $_ } | Select-Object -First 1
        if ($exitCode -ne 0 -or $diagnostic) {
            throw "APP $($target.Name) build failed (exit=$exitCode; diagnostic=$diagnostic)."
        }

        foreach ($relativeArtifact in @($target.Artifact, $target.CompilerArtifact, 'dist\build\app\app-service.js')) {
            $artifactPath = Join-Path $appPath $relativeArtifact
            if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf) -or
                (Get-Item -LiteralPath $artifactPath).Length -eq 0) {
                throw "APP $($target.Name) build reported success but expected CLI output is missing: $artifactPath"
            }
            if ((Get-Item -LiteralPath $artifactPath).LastWriteTime -lt $buildStartedAt) {
                throw "APP $($target.Name) build reported success but expected CLI output was not refreshed: $artifactPath"
            }
        }
    }
} finally {
    Pop-Location
}
