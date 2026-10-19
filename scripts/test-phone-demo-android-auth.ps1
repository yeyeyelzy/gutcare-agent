[CmdletBinding()]
param(
    [string]$Serial,
    [switch]$KeepServices
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$androidRoot = Join-Path $root 'android'
$evidenceRoot = Join-Path $androidRoot 'build\emulator-evidence'
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$evidenceDir = Join-Path $evidenceRoot "phone-demo-auth-$runId"
$summaryPath = Join-Path $evidenceDir 'summary.json'
$junitSummaryPath = Join-Path $evidenceDir 'junit-summary.json'
$screenshotPath = Join-Path $evidenceDir 'emulator.png'
$adb = Get-Command adb -ErrorAction SilentlyContinue
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $adb) { throw 'Android platform-tools adb is required.' }
if (-not $docker) { throw 'Docker CLI is required.' }

$startedServices = $false
$preexistingContainers = @()
$startedContainers = @()
$lifecycleMutex = [System.Threading.Mutex]::new($false, 'Local\GutCarePhoneDemoAndroidAuth')
$lifecycleLockAcquired = $false
$testExitCode = 1
$testOutput = @()
$testStartedAt = Get-Date
$emulatorSerial = $null
$mappedDrive = $null
$mappedByThisScript = $false
$startupAttempted = $false
$cleanupOutcome = 'not_attempted'
New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null

function Get-PhoneDemoContainerSnapshot {
    $ids = @(& $docker.Source ps -aq --no-trunc --filter 'label=com.docker.compose.project=gutcare-phone-demo')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect the local phone-demo Compose project.' }
    $snapshot = @()
    foreach ($id in $ids) {
        if (-not $id) { continue }
        $description = & $docker.Source inspect --format '{{.Id}}|{{.State.Status}}|{{ index .Config.Labels "com.docker.compose.project" }}' $id
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect a phone-demo container.' }
        $parts = ([string]$description).Trim().Split('|', 3)
        if ($parts.Count -ne 3 -or $parts[2] -ne 'gutcare-phone-demo') { throw 'Phone-demo filter returned a container with an unexpected project label.' }
        $snapshot += [pscustomobject]@{ Id = $parts[0]; State = $parts[1] }
    }
    return @($snapshot | Sort-Object Id)
}

function Test-SameContainerIds([object[]]$Left, [object[]]$Right) {
    $leftIds = @($Left | ForEach-Object { [string]$_.Id } | Sort-Object)
    $rightIds = @($Right | ForEach-Object { [string]$_.Id } | Sort-Object)
    return (($leftIds.Count -eq $rightIds.Count) -and (($leftIds -join ',') -ceq ($rightIds -join ',')))
}

function Assert-PhoneDemoReady([object[]]$Snapshot) {
    $healthOk = $false
    try {
        $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health/live' -Method Get -TimeoutSec 5
        $healthOk = $response.StatusCode -eq 200
    } catch { $healthOk = $false }
    if ($Snapshot.Count -eq 0 -or @($Snapshot | Where-Object { $_.State -ne 'running' }).Count -gt 0 -or -not $healthOk) {
        throw 'Phone-demo is not ready (all project containers must be running and health/live must return 200); existing resources were left unchanged.'
    }
}

function Write-SafeJUnitSummary([datetime]$Since) {
    $safe = [ordered]@{
        suite = 'PhoneDemoAuthLiveContractTest'
        tests = 0
        passed = 0
        failures = 0
        errors = 0
        skipped = 0
        junit_available = $false
    }
    $resultsRoot = Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug'
    $resultFiles = @(Get-ChildItem -LiteralPath $resultsRoot -Filter '*.xml' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $Since })
    foreach ($resultFile in $resultFiles) {
        try {
            [xml]$junit = [System.IO.File]::ReadAllText($resultFile.FullName)
            $case = @($junit.SelectNodes('//testcase') | Where-Object { $_.GetAttribute('classname') -eq 'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest' }) | Select-Object -First 1
            if (-not $case) { continue }
            $safe.junit_available = $true
            $safe.tests = 1
            $failureNode = $case.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error') } | Select-Object -First 1
            $skippedNode = $case.ChildNodes | Where-Object { $_.LocalName -eq 'skipped' } | Select-Object -First 1
            if ($failureNode) {
                if ($failureNode.LocalName -eq 'failure') { $safe.failures = 1 } else { $safe.errors = 1 }
                # Only retain structured diagnostics emitted by failSafe; never copy JUnit text or body.
                $message = [string]$failureNode.GetAttribute('message')
                $pattern = '^(?<stage>registration|verification|login/profile|refresh/profile|logout) failed: status=(?<status>\d{3}|none) code=(?<code>[A-Z0-9_]+|none)(?: request_id=(?<requestId>[0-9a-fA-F-]{36}))?$'
                if ($message -match $pattern) {
                    $safe.diagnostic = [ordered]@{
                        stage = $Matches.stage
                        status = $Matches.status
                        code = $Matches.code
                        request_id = $Matches.requestId
                    }
                } else {
                    $safe.diagnostic = 'Test failed; details suppressed.'
                }
            } elseif ($skippedNode) {
                $safe.skipped = 1
                $safe.diagnostic = 'Live test skipped.'
            } else {
                $safe.passed = 1
            }
            break
        } catch {
            # Malformed reports are deliberately not copied into evidence.
        }
    }
    [System.IO.File]::WriteAllText($junitSummaryPath, ($safe | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    return $safe
}

try {
    $lifecycleLockAcquired = $lifecycleMutex.WaitOne(0)
    if (-not $lifecycleLockAcquired) { throw 'Another Android phone-demo auth lifecycle is active; refusing concurrent Compose operations.' }
    $preexistingContainers = @(Get-PhoneDemoContainerSnapshot)
    if ($preexistingContainers.Count -gt 0) {
        Assert-PhoneDemoReady $preexistingContainers
    } else {
        $startupAttempted = $true
        & (Join-Path $PSScriptRoot 'phone-demo-up.ps1')
        if ($LASTEXITCODE -ne 0) { throw 'Phone-demo startup failed.' }
        $startedServices = $true
        $startedContainers = @(Get-PhoneDemoContainerSnapshot)
        if ($startedContainers.Count -eq 0) { throw 'Phone-demo startup returned without creating project containers.' }
        Assert-PhoneDemoReady $startedContainers
    }
    $devices = @(& $adb.Source devices)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate adb devices.' }
    $emulators = @($devices | ForEach-Object {
        if ($_ -match '^(emulator-\d+)\s+device$') { $Matches[1] }
    })
    if ($Serial) {
        if ($Serial -notmatch '^emulator-\d+$' -or $Serial -notin $emulators) { throw 'Requested serial is not a connected Android emulator.' }
        $emulatorSerial = $Serial
    } elseif ($emulators.Count -eq 1) {
        $emulatorSerial = $emulators[0]
    } else {
        throw 'Exactly one Android Studio emulator must be connected, or pass -Serial emulator-NNNN.'
    }

    $debugApiBaseUrl = 'http://10.0.2.2:8000/api/v1/'
    $gradleCommonArgs = @('--no-daemon', "-PdebugApiBaseUrl=$debugApiBaseUrl")
    $gradleArgs = @('connectedDebugAndroidTest') + $gradleCommonArgs + @("-Pandroid.injected.device.serial=$emulatorSerial", '-Pandroid.testInstrumentationRunnerArguments.phoneDemoLive=true')
    $testStartedAt = Get-Date
    $repoPath = (Resolve-Path $root).Path
    $existingMappings = @(& subst)
    foreach ($driveLetter in @('S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z')) {
        if ((Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue) -or ($existingMappings | Where-Object { $_ -match "^${driveLetter}:\\: => " })) { continue }
        $mappedDrive = "${driveLetter}:"
        break
    }
    if (-not $mappedDrive) { throw 'No unused ASCII drive letter is available for the Android build.' }
    & subst $mappedDrive $repoPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create a temporary ASCII drive mapping for Gradle.' }
    $mappedByThisScript = $true
    $mappedAndroidRoot = Join-Path "$mappedDrive\" 'android'
    if (-not (Test-Path -LiteralPath (Join-Path $mappedAndroidRoot 'settings.gradle.kts'))) { throw 'The ASCII drive mapping does not expose the Android project.' }
    Push-Location $mappedAndroidRoot
    try {
        # connectedDebugAndroidTest may uninstall the tested app during teardown.
        # Build the same debug variant with the same API base URL, then reinstall
        # it before opening the app for screenshot evidence.
        $buildOutput = @(& '.\gradlew.bat' assembleDebug @gradleCommonArgs 2>&1)
        if ($LASTEXITCODE -ne 0) { throw 'Android debug app build failed; credentials are suppressed.' }
        $testOutput = @(& '.\gradlew.bat' @gradleArgs 2>&1)
        $testExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    # Gradle may echo runner arguments. Keep its output transient and publish only a status summary.
    if ($testExitCode -ne 0) { throw 'Android live auth instrumentation failed; inspect the Gradle result locally (credentials are suppressed).' }

    $testResultsRoot = Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug'
    $resultFiles = @(Get-ChildItem -LiteralPath $testResultsRoot -Filter '*.xml' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $testStartedAt })
    $targetCase = $null
    foreach ($resultFile in $resultFiles) {
        [xml]$junit = [System.IO.File]::ReadAllText($resultFile.FullName)
        $targetCase = @($junit.SelectNodes('//testcase') | Where-Object { $_.GetAttribute('classname') -eq 'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest' }) | Select-Object -First 1
        if ($targetCase) { break }
    }
    if (-not $targetCase) { throw 'Successful Gradle exit did not include the opted-in live auth JUnit case.' }
    if ($targetCase.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error', 'skipped') }) { throw 'The live auth JUnit case did not execute as a passing test.' }
    $junitSummary = [ordered]@{
        suite = 'PhoneDemoAuthLiveContractTest'
        tests = 1
        passed = 1
        failures = 0
        errors = 0
        skipped = 0
    }
    [System.IO.File]::WriteAllText($junitSummaryPath, ($junitSummary | ConvertTo-Json -Depth 4), [System.Text.UTF8Encoding]::new($false))

    $debugApk = Join-Path $androidRoot 'app\build\outputs\apk\debug\app-debug.apk'
    if (-not (Test-Path -LiteralPath $debugApk)) { throw 'Built Android debug APK is missing.' }
    & $adb.Source -s $emulatorSerial install -r $debugApk | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the debug app for the post-test screenshot.' }
    & $adb.Source -s $emulatorSerial shell am start -n com.gutcare.app/.MainActivity | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not open the app for the post-test screenshot.' }
    $welcomeVisible = $false
    $uiDumpPath = '/sdcard/gutcare-live-auth-ui.xml'
    $welcomeWaitDeadline = (Get-Date).AddSeconds(180)
    while ((Get-Date) -lt $welcomeWaitDeadline) {
        # Inspect only whether the known welcome heading is present. UI hierarchy
        # output stays on-device and is never copied to the console or evidence.
        & $adb.Source -s $emulatorSerial shell uiautomator dump $uiDumpPath 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            & $adb.Source -s $emulatorSerial shell grep -q 'A.LITTLE.CARE,.EVERY.DAY' $uiDumpPath | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $welcomeVisible = $true
                break
            }
        }
        Start-Sleep -Seconds 3
    }
    if (-not $welcomeVisible) { throw 'Welcome screen did not become visible before the screenshot timeout.' }
    & $adb.Source -s $emulatorSerial shell screencap -p /sdcard/gutcare-live-auth.png | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not capture emulator screenshot.' }
    & $adb.Source -s $emulatorSerial pull /sdcard/gutcare-live-auth.png $screenshotPath | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $screenshotPath)) { throw 'Could not retain emulator screenshot evidence.' }

    $summary = [ordered]@{
        schema_version = '1.0'
        test_id = 'T01k'
        status = 'passed'
        environment = 'local phone-demo Docker Compose; Android emulator loopback bridge 10.0.2.2'
        api_base = 'http://10.0.2.2:8000/api/v1/'
        emulator_serial = $emulatorSerial
        executed_at = (Get-Date).ToUniversalTime().ToString('o')
        compose_containers_before = @($preexistingContainers)
        compose_containers_started = @($startedContainers)
        evidence = @('emulator.png', 'junit-summary.json', 'Android Gradle connectedDebugAndroidTest XML retained under android/app/build/outputs/androidTest-results')
        secrets_recorded = $false
    }
    [System.IO.File]::WriteAllText($summaryPath, ($summary | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    Write-Host "Phone-demo Android auth live contract passed. Safe evidence: $summaryPath"
} catch {
    $safeJUnit = Write-SafeJUnitSummary $testStartedAt
    $summary = [ordered]@{
        schema_version = '1.0'
        test_id = 'T01k'
        status = 'failed'
        environment = 'local phone-demo Docker Compose; Android emulator loopback bridge 10.0.2.2'
        executed_at = (Get-Date).ToUniversalTime().ToString('o')
        compose_containers_before = @($preexistingContainers)
        compose_containers_started = @($startedContainers)
        gradle_exit_code = $testExitCode
        junit_summary = 'junit-summary.json'
        failure = 'See local command output; response bodies and credentials are not copied into evidence.'
        secrets_recorded = $false
    }
    [System.IO.File]::WriteAllText($summaryPath, ($summary | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
    throw
} finally {
    try {
        if ($startedServices -and -not $KeepServices -and $preexistingContainers.Count -eq 0 -and $startedContainers.Count -gt 0) {
            $currentContainers = @(Get-PhoneDemoContainerSnapshot)
            if (Test-SameContainerIds $startedContainers $currentContainers) {
                $expectedIds = @($startedContainers | ForEach-Object { $_.Id })
                try {
                    & (Join-Path $PSScriptRoot 'phone-demo-down.ps1') -ExpectedContainerIds $expectedIds
                    if ($LASTEXITCODE -ne 0) { throw 'phone-demo-down.ps1 returned a failure code.' }
                    $cleanupOutcome = 'stopped_verified_startup_ids'
                } catch {
                    $cleanupOutcome = 'down_failed'
                    Write-Warning 'Phone-demo shutdown failed; inspect the exact container IDs recorded for this run.'
                }
            } else {
                $cleanupOutcome = 'refused_changed_container_ids'
                Write-Warning 'Phone-demo cleanup refused: current project container IDs differ from the IDs created by this run.'
            }
        } elseif ($startupAttempted -and $startedContainers.Count -eq 0) {
            $cleanupOutcome = 'refused_unverified_startup_ids'
            Write-Warning 'Phone-demo cleanup refused: startup container IDs were not captured, so ownership cannot be proven.'
        } elseif ($KeepServices -and $startedServices) {
            $cleanupOutcome = 'kept_by_request'
        } elseif ($preexistingContainers.Count -gt 0) {
            $cleanupOutcome = 'preexisting_project_preserved'
        }
    } finally {
        if ($mappedByThisScript) { subst $mappedDrive /D }
        if ($lifecycleLockAcquired) { $lifecycleMutex.ReleaseMutex() }
        $lifecycleMutex.Dispose()
        if (Test-Path -LiteralPath $summaryPath) {
            $finalSummary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
            $finalSummary | Add-Member -NotePropertyName compose_cleanup -NotePropertyValue $cleanupOutcome -Force
            [System.IO.File]::WriteAllText($summaryPath, ($finalSummary | ConvertTo-Json -Depth 8), [System.Text.UTF8Encoding]::new($false))
        }
    }
}
