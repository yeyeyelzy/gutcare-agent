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
$script:classRunSummaries = [System.Collections.Generic.List[object]]::new()
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
        $description = & $docker.Source inspect --format '{{.Id}}|{{json .State}}|{{ index .Config.Labels "com.docker.compose.service" }}|{{ index .Config.Labels "com.docker.compose.project" }}' $id
        if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect a phone-demo container.' }
        $parts = ([string]$description).Trim().Split('|', 4)
        if ($parts.Count -ne 4 -or $parts[3] -ne 'gutcare-phone-demo') { throw 'Phone-demo filter returned a container with an unexpected project label.' }
        try { $containerState = $parts[1] | ConvertFrom-Json -ErrorAction Stop } catch { throw 'Unable to parse a phone-demo container state.' }
        $health = if ($containerState.Health) { [string]$containerState.Health.Status } else { 'none' }
        $snapshot += [pscustomobject]@{ Id = $parts[0]; State = [string]$containerState.Status; ExitCode = [int]$containerState.ExitCode; Health = $health; Service = $parts[2] }
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
    $ignoredOptionalStopped = [System.Collections.Generic.List[string]]::new()
    $requiredServices = @('api', 'postgres', 'redis', 'mailpit', 'minio', 'clamav')
    $presentRequiredServices = @($Snapshot | Where-Object { $_.Service -in $requiredServices } | ForEach-Object { $_.Service } | Sort-Object -Unique)
    if (($presentRequiredServices -join ',') -cne (($requiredServices | Sort-Object) -join ',')) {
        throw 'Phone-demo is not ready because a required core service is missing.'
    }
    $notReady = @($Snapshot | Where-Object {
        if ($_.Service -in $requiredServices -and $_.State -eq 'running' -and $_.Health -eq 'healthy') { return $false }
        if ($_.Service -in @('agent', 'analysis-dispatcher') -and $_.State -eq 'running') { return $false }
        if ($_.State -eq 'exited' -and $_.ExitCode -eq 0 -and $_.Service -eq 'minio-init') { return $false }
        if ($_.State -eq 'exited' -and $_.Service -in @('agent', 'analysis-dispatcher') -and $_.ExitCode -in @(0, 137)) {
            $ignoredOptionalStopped.Add([string]$_.Service)
            return $false
        }
        return $true
    })
    if ($Snapshot.Count -eq 0 -or $notReady.Count -gt 0 -or -not $healthOk) {
        throw 'Phone-demo is not ready (services must be running, with only the successful minio-init one-shot allowed to exit, and health/live must return 200); existing resources were left unchanged.'
    }
    $script:ignoredOptionalStopped = @($ignoredOptionalStopped | Sort-Object -Unique)
}

function Write-SafeJUnitSummary([datetime]$Since) {
    $safe = [ordered]@{
        suite = 'PhoneDemoAuthLive'
        tests = 0
        passed = 0
        failures = 0
        errors = 0
        skipped = 0
        junit_available = $false
    }
    if ($script:classRunSummaries.Count -gt 0) {
        $safe.junit_available = $true
        $safe.classes = @($script:classRunSummaries.ToArray())
        foreach ($classResult in $script:classRunSummaries) {
            $safe.tests += $classResult.tests
            $safe.passed += $classResult.passed
            $safe.failures += $classResult.failures
            $safe.errors += $classResult.errors
            $safe.skipped += $classResult.skipped
            if ($classResult.diagnostic) { $safe.diagnostic = $classResult.diagnostic }
        }
        [System.IO.File]::WriteAllText($junitSummaryPath, ($safe | ConvertTo-Json -Depth 6), [System.Text.UTF8Encoding]::new($false))
        return $safe
    }
    $resultsRoot = Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug'
    $resultFiles = @(Get-ChildItem -LiteralPath $resultsRoot -Filter '*.xml' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $Since })
    foreach ($resultFile in $resultFiles) {
        try {
            [xml]$junit = [System.IO.File]::ReadAllText($resultFile.FullName)
            $cases = @($junit.SelectNodes('//testcase') | Where-Object {
                $_.GetAttribute('classname') -in @(
                    'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest',
                    'com.gutcare.app.ui.auth.PhoneDemoAuthUiLiveTest'
                )
            })
            if ($cases.Count -eq 0) { continue }
            $safe.junit_available = $true
            foreach ($case in $cases) {
                $safe.tests++
                $failureNode = $case.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error') } | Select-Object -First 1
                $skippedNode = $case.ChildNodes | Where-Object { $_.LocalName -eq 'skipped' } | Select-Object -First 1
                if ($failureNode) {
                    if ($failureNode.LocalName -eq 'failure') { $safe.failures++ } else { $safe.errors++ }
                    $safe.diagnostic = 'Test failed; details suppressed.'
                    $safeDiagnostic = [regex]::Match(
                        ($failureNode.GetAttribute('message') + ' ' + $failureNode.InnerText),
                        'safe checkpoint: ([a-z_]+); safe error codes: ([A-Z0-9_, ]+); safe validation fields: ([A-Za-z0-9_.,]+); safe auth reason: ([A-Z0-9_, ]+); safe operation_state: (loading|error|accepted|none)'
                    )
                    if ($safeDiagnostic.Success) {
                        $stage = $safeDiagnostic.Groups[1].Value
                        $codes = $safeDiagnostic.Groups[2].Value.Trim().TrimEnd(',')
                        $fields = $safeDiagnostic.Groups[3].Value.Trim().TrimEnd(',')
                        $reason = $safeDiagnostic.Groups[4].Value.Trim().TrimEnd(',')
                        $operationState = $safeDiagnostic.Groups[5].Value
                        if ($stage -match '^[a-z_]+$' -and $codes -match '^(none|[A-Z0-9_, ]+)$' -and
                            $fields -match '^(none|[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*(,[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*)*)$' -and
                            $reason -match '^(none|[A-Z0-9_, ]+)$' -and $operationState -in @('loading', 'error', 'accepted', 'none')) {
                            $safe.diagnostic = "stage=$stage; safe_error_codes=$codes; validation_locations=$fields; safe_auth_reason=$reason; operation_state=$operationState"
                        }
                    }
                } elseif ($skippedNode) {
                    $safe.skipped++
                    $safe.diagnostic = 'Live test skipped.'
                } else {
                    $safe.passed++
                }
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
    if ($script:ignoredOptionalStopped.Count -gt 0) {
        Write-Host ('Phone-demo readiness ignored_optional_stopped=' + ($script:ignoredOptionalStopped -join ','))
    }
    $devices = @(& $adb.Source devices)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate adb devices.' }
    $deviceSerials = @($devices | ForEach-Object {
        if ($_ -match '^(emulator-\d+|127\.0\.0\.1:\d+)\s+device(?:\s|$)') { $Matches[1] }
    })
    $emulators = @($deviceSerials | Where-Object {
        if ($_ -match '^emulator-\d+$') { return $true }
        $qemu = @(& $adb.Source -s $_ shell getprop ro.kernel.qemu 2>$null)
        return ($LASTEXITCODE -eq 0 -and (($qemu -join '').Trim() -eq '1'))
    })
    if ($Serial) {
        if ($Serial -notin $emulators) { throw 'Requested serial is not a connected Android emulator.' }
        $emulatorSerial = $Serial
    } elseif ($emulators.Count -eq 1) {
        $emulatorSerial = $emulators[0]
    } else {
        throw 'Exactly one Android Studio emulator must be connected, or pass its -Serial value.'
    }

    $debugApiBaseUrl = 'http://10.0.2.2:8000/api/v1/'
    $gradleCommonArgs = @('--no-daemon', "-PdebugApiBaseUrl=$debugApiBaseUrl")
    $targetClassNames = @(
        'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest',
        'com.gutcare.app.ui.auth.PhoneDemoAuthUiLiveTest'
    )
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
        $targetCases = @()
        $testExitCode = 0
        foreach ($className in $targetClassNames) {
            $classStartedAt = Get-Date
            $classGradleArgs = @('connectedDebugAndroidTest') + $gradleCommonArgs + @(
                "-Pandroid.injected.device.serial=$emulatorSerial",
                '-Pandroid.testInstrumentationRunnerArguments.phoneDemoLive=true',
                "-Pandroid.testInstrumentationRunnerArguments.class=$className"
            )
            $testOutput = @(& '.\gradlew.bat' @classGradleArgs 2>&1)
            $classExitCode = $LASTEXITCODE
            if ($classExitCode -ne 0) { $testExitCode = $classExitCode }

            $classCases = @()
            $classResultFiles = @(Get-ChildItem -LiteralPath (Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug') -Filter '*.xml' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $classStartedAt })
            foreach ($resultFile in $classResultFiles) {
                try {
                    [xml]$junit = [System.IO.File]::ReadAllText($resultFile.FullName)
                    $classCases += @($junit.SelectNodes('//testcase') | Where-Object { $_.GetAttribute('classname') -eq $className })
                } catch {
                    # Malformed reports are not surfaced; the missing case fails closed below.
                }
            }
            $targetCases += $classCases
            foreach ($case in $classCases) {
                $failureNode = $case.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error') } | Select-Object -First 1
                $skippedNode = $case.ChildNodes | Where-Object { $_.LocalName -eq 'skipped' } | Select-Object -First 1
                $classResult = [ordered]@{
                    class_name = $className
                    test_name = $case.GetAttribute('name')
                    tests = 1
                    passed = 0
                    failures = 0
                    errors = 0
                    skipped = 0
                    diagnostic = $null
                }
                if ($failureNode) {
                    if ($failureNode.LocalName -eq 'failure') { $classResult.failures = 1 } else { $classResult.errors = 1 }
                    $safeDiagnostic = [regex]::Match(
                        ($failureNode.GetAttribute('message') + ' ' + $failureNode.InnerText),
                        'safe checkpoint: ([a-z_]+); safe error codes: ([A-Z0-9_, ]+); safe validation fields: ([A-Za-z0-9_.,]+); safe auth reason: ([A-Z0-9_, ]+); safe operation_state: (loading|error|accepted|none)'
                    )
                    if ($safeDiagnostic.Success) {
                        $safeStage = $safeDiagnostic.Groups[1].Value
                        $safeCodes = $safeDiagnostic.Groups[2].Value.Trim().TrimEnd(',')
                        $safeFields = $safeDiagnostic.Groups[3].Value.Trim().TrimEnd(',')
                        $safeReason = $safeDiagnostic.Groups[4].Value.Trim().TrimEnd(',')
                        $operationState = $safeDiagnostic.Groups[5].Value
                        if ($safeStage -match '^[a-z_]+$' -and $safeCodes -match '^(none|[A-Z0-9_, ]+)$' -and
                            $safeFields -match '^(none|[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*(,[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*)*)$' -and
                            $safeReason -match '^(none|[A-Z0-9_, ]+)$' -and $operationState -in @('loading', 'error', 'accepted', 'none')) {
                            $classResult.diagnostic = "stage=$safeStage; safe_error_codes=$safeCodes; validation_locations=$safeFields; safe_auth_reason=$safeReason; operation_state=$operationState"
                        }
                    }
                    if (-not $classResult.diagnostic) { $classResult.diagnostic = 'Test failed; details suppressed.' }
                } elseif ($skippedNode) {
                    $classResult.skipped = 1
                    $classResult.diagnostic = 'Live test skipped.'
                } else {
                    $classResult.passed = 1
                }
                $script:classRunSummaries.Add($classResult)
            }
            $classEvidenceName = if ($className -eq 'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest') { 'repository' } else { 'ui' }
            $classEvidence = [ordered]@{
                suite = 'PhoneDemoAuthLive'
                class_name = $className
                tests = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Measure-Object -Property tests -Sum).Sum
                passed = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Measure-Object -Property passed -Sum).Sum
                failures = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Measure-Object -Property failures -Sum).Sum
                errors = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Measure-Object -Property errors -Sum).Sum
                skipped = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Measure-Object -Property skipped -Sum).Sum
                diagnostic = @($script:classRunSummaries | Where-Object { $_.class_name -eq $className } | Select-Object -ExpandProperty diagnostic -ErrorAction SilentlyContinue | Where-Object { $_ }) | Select-Object -Last 1
                junit_available = ($classCases.Count -gt 0)
            }
            $classEvidencePath = Join-Path $evidenceDir "junit-$classEvidenceName-summary.json"
            [System.IO.File]::WriteAllText($classEvidencePath, ($classEvidence | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
            if ($classExitCode -ne 0 -or $classCases.Count -ne 1 -or @($classCases | Where-Object { $_.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error', 'skipped') } }).Count -gt 0) {
                $testExitCode = if ($classExitCode -ne 0) { $classExitCode } else { 1 }
                break
            }
        }
    } finally { Pop-Location }
    # Gradle may echo runner arguments. Keep its output transient and publish only a status summary.
    if ($testExitCode -ne 0) { throw 'Android live auth instrumentation failed; inspect the safe JUnit summary (credentials are suppressed).' }

    $testResultsRoot = Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug'
    $resultFiles = @(Get-ChildItem -LiteralPath $testResultsRoot -Filter '*.xml' -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $testStartedAt })
    $targetCases = @()
    foreach ($resultFile in $resultFiles) {
        [xml]$junit = [System.IO.File]::ReadAllText($resultFile.FullName)
        $targetCases += @($junit.SelectNodes('//testcase') | Where-Object {
            $_.GetAttribute('classname') -in @(
                'com.gutcare.app.core.network.PhoneDemoAuthLiveContractTest',
                'com.gutcare.app.ui.auth.PhoneDemoAuthUiLiveTest'
            )
        })
    }
    $completedClasses = @($targetCases | ForEach-Object { $_.GetAttribute('classname') } | Sort-Object -Unique)
    if ($targetCases.Count -ne 2 -or $completedClasses.Count -ne 2) { throw 'Successful Gradle exit did not include both separately invoked live auth JUnit classes.' }
    if (@($targetCases | Where-Object { $_.ChildNodes | Where-Object { $_.LocalName -in @('failure', 'error', 'skipped') } }).Count -gt 0) { throw 'A live auth JUnit case did not execute as a passing test.' }
    $junitSummary = [ordered]@{
        suite = 'PhoneDemoAuthLive'
        tests = 2
        passed = 2
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
