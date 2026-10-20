param(
    [string]$SdkRoot,
    [string]$GradleUserHome,
    [string]$ProjectCacheDir,
    [string]$JavaTempDir
)

$ErrorActionPreference = "Stop"

$androidRoot = (Resolve-Path $PSScriptRoot).Path
$repoRoot = Split-Path -Parent $androidRoot
$sdkRoot = if ($SdkRoot) { $SdkRoot } elseif ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
$mappedDrive = $null
$existingMappings = @(& subst)
foreach ($letter in 'Z'..'D') {
    if ((Get-PSDrive -Name $letter -ErrorAction SilentlyContinue) -or ($existingMappings | Where-Object { $_ -match "^${letter}:\\: => " })) { continue }
    $mappedDrive = "${letter}:"
    break
}
if (-not $mappedDrive) { throw "No unused drive letter is available for an ASCII Gradle path." }

$cacheRoot = Join-Path $env:SystemDrive 'GutCare\gradle'
$gradleHome = if ($GradleUserHome) { $GradleUserHome } elseif ($env:GRADLE_USER_HOME) { $env:GRADLE_USER_HOME } else { Join-Path $cacheRoot 'user-home' }
$projectCache = if ($ProjectCacheDir) { $ProjectCacheDir } else { Join-Path $cacheRoot 'project-cache' }
$javaTemp = if ($JavaTempDir) { $JavaTempDir } else { Join-Path $cacheRoot 'tmp' }
New-Item -ItemType Directory -Force -Path $gradleHome, $projectCache, $javaTemp | Out-Null

$previousGradleHome = $env:GRADLE_USER_HOME
$previousSdkRoot = $env:ANDROID_SDK_ROOT
$previousAndroidHome = $env:ANDROID_HOME
$previousJavaToolOptions = $env:JAVA_TOOL_OPTIONS
$mappedByThisScript = $false
$exitCode = 1

try {
    subst $mappedDrive $repoRoot
    $mappedByThisScript = $true
    $mappedAndroidRoot = Join-Path "$mappedDrive\" 'android'
    if (-not (Test-Path (Join-Path $mappedAndroidRoot 'settings.gradle.kts'))) { throw "Temporary ASCII mapping does not expose the Android project." }

    $env:GRADLE_USER_HOME = $gradleHome
    $env:ANDROID_SDK_ROOT = $sdkRoot
    $env:ANDROID_HOME = $sdkRoot
    $env:JAVA_TOOL_OPTIONS = "-Djava.io.tmpdir=$javaTemp"
    if ($previousJavaToolOptions) {
        $env:JAVA_TOOL_OPTIONS = "$previousJavaToolOptions $env:JAVA_TOOL_OPTIONS"
    }

    Set-Location $mappedAndroidRoot
    & ".\gradlew.bat" -p $mappedAndroidRoot --project-cache-dir $projectCache assembleDebug test lint --no-daemon
    $exitCode = $LASTEXITCODE
}
finally {
    if ($previousGradleHome) {
        $env:GRADLE_USER_HOME = $previousGradleHome
    }
    else {
        Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
    }
    if ($previousSdkRoot) { $env:ANDROID_SDK_ROOT = $previousSdkRoot } else { Remove-Item Env:ANDROID_SDK_ROOT -ErrorAction SilentlyContinue }
    if ($previousAndroidHome) { $env:ANDROID_HOME = $previousAndroidHome } else { Remove-Item Env:ANDROID_HOME -ErrorAction SilentlyContinue }
    if ($previousJavaToolOptions) {
        $env:JAVA_TOOL_OPTIONS = $previousJavaToolOptions
    }
    else {
        Remove-Item Env:JAVA_TOOL_OPTIONS -ErrorAction SilentlyContinue
    }

    Set-Location $repoRoot
    if ($mappedByThisScript) {
        subst $mappedDrive /D
    }
}

exit $exitCode
