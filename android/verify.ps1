$ErrorActionPreference = "Stop"

$androidRoot = (Resolve-Path $PSScriptRoot).Path
$repoRoot = Split-Path -Parent $androidRoot
$mappedDrive = "R:"
if (Get-PSDrive -Name "R" -ErrorAction SilentlyContinue) {
    throw "R: is already in use; verification stopped without changing the mapping."
}

$gradleHome = "C:\gutcare-gradle-home"
$javaTemp = "C:\gutcare-gradle-tmp"
New-Item -ItemType Directory -Force -Path $gradleHome, $javaTemp | Out-Null

$previousGradleHome = $env:GRADLE_USER_HOME
$previousJavaToolOptions = $env:JAVA_TOOL_OPTIONS
$mappedByThisScript = $false
$exitCode = 1

try {
    subst $mappedDrive $repoRoot
    $mappedByThisScript = $true
    $mappingLine = subst | Where-Object { $_ -match "^R:\\: => " }
    if (-not $mappingLine) {
        throw "Could not verify the R: mapping created for this repository root."
    }

    $env:GRADLE_USER_HOME = $gradleHome
    $env:JAVA_TOOL_OPTIONS = "-Djava.io.tmpdir=$javaTemp"
    if ($previousJavaToolOptions) {
        $env:JAVA_TOOL_OPTIONS = "$previousJavaToolOptions $env:JAVA_TOOL_OPTIONS"
    }

    Set-Location "R:\android"
    & ".\gradlew.bat" -p "R:\android" assembleDebug test lint --no-daemon
    $exitCode = $LASTEXITCODE
}
finally {
    if ($previousGradleHome) {
        $env:GRADLE_USER_HOME = $previousGradleHome
    }
    else {
        Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
    }
    if ($previousJavaToolOptions) {
        $env:JAVA_TOOL_OPTIONS = $previousJavaToolOptions
    }
    else {
        Remove-Item Env:JAVA_TOOL_OPTIONS -ErrorAction SilentlyContinue
    }

    Set-Location $repoRoot
    if ($mappedByThisScript) {
        $mappingLine = subst | Where-Object { $_ -match "^R:\\: => " }
        if ($mappingLine) {
            subst R: /D
        }
    }
}

exit $exitCode
