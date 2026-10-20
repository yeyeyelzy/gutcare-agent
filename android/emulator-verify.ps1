param([string]$SdkRoot)

$ErrorActionPreference = 'Stop'

# This harness uses a private adb server and fixed emulator console port. Physical
# devices and emulator instances owned by Android Studio are never enumerated.
$androidRoot = (Resolve-Path $PSScriptRoot).Path
$repoRoot = Split-Path -Parent $androidRoot
$mappedDrive = $null
$sdkRoot = if ($SdkRoot) { $SdkRoot } elseif ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
$avdName = 'GutCare_API_37'
$adbPort = 5038
$emulatorPort = 5580
$serial = "emulator-$emulatorPort"
$systemImage = 'system-images\android-37.0\google_apis_playstore\x86_64\system.img'
$avdDir = Join-Path $env:USERPROFILE ".android\avd\$avdName.avd"
$avdConfig = Join-Path $avdDir 'config.ini'
$avdIni = Join-Path $env:USERPROFILE ".android\avd\$avdName.ini"
$evidenceRoot = Join-Path $androidRoot 'build\emulator-evidence'
$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$evidenceDir = Join-Path $evidenceRoot $runId
$screenshotPath = Join-Path $evidenceDir 'emulator.png'
$summaryPath = Join-Path $evidenceDir 'summary.json'

foreach ($requiredPath in @(
    (Join-Path $sdkRoot 'emulator\emulator.exe'),
    (Join-Path $sdkRoot 'platform-tools\adb.exe'),
    (Join-Path $sdkRoot 'cmdline-tools\latest\bin\avdmanager.bat'),
    (Join-Path $sdkRoot $systemImage)
)) {
    if (-not (Test-Path $requiredPath)) { throw "Required Android SDK component not found: $requiredPath" }
}

$emulatorExe = Join-Path $sdkRoot 'emulator\emulator.exe'
$adbExe = Join-Path $sdkRoot 'platform-tools\adb.exe'
$avdManager = Join-Path $sdkRoot 'cmdline-tools\latest\bin\avdmanager.bat'
$createdAvd = $false
$emulatorProcess = $null
$startedAdbServer = $false
$mappedByThisScript = $false
$previousAdbPort = $env:ANDROID_ADB_SERVER_PORT
$previousSdkRoot = $env:ANDROID_SDK_ROOT
$previousAndroidHome = $env:ANDROID_HOME
$testExitCode = 1
$testCount = 0
$failureCount = 0
$errorCount = 0
$status = 'failed'
$actualLocale = ''
$localeSetting = ''
$localeProperty = ''
$actualFontScale = ''
$foregroundActivity = ''
$activityLaunchOutput = ''
$installedPackageOutput = ''
$resolvedActivityOutput = ''

function Invoke-PrivateAdb {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]] $AdbArgs)
    & $adbExe @AdbArgs
    if ($LASTEXITCODE -ne 0) { throw "adb command failed with exit code $LASTEXITCODE" }
}

function Get-AvdNameForSerial {
    param([string] $DeviceSerial)
    $output = & $adbExe -s $DeviceSerial emu avd name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
    return ([string]$output[0]).Trim()
}

function Test-LaunchedEmulatorIdentity {
    if (-not $script:emulatorProcess) { return $false }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($script:emulatorProcess.Id)" -ErrorAction SilentlyContinue
    if (-not $processInfo -or $processInfo.Name -ne 'emulator.exe') { return $false }
    return ($processInfo.CommandLine -match '(?i)(^|\s)-avd\s+"?GutCare_API_37("|\s|$)')
}

try {
    if (-not (Test-Path $avdConfig)) {
        $createOutput = & $avdManager create avd --name $avdName --package 'system-images;android-37.0;google_apis_playstore;x86_64' --device pixel_7 --sdcard 2G 2>&1
        if ($LASTEXITCODE -ne 0) { throw "avdmanager could not create $avdName : $($createOutput -join ' ')" }
        $createdAvd = $true
    }
    if (-not (Test-Path $avdConfig) -or -not (Test-Path $avdIni)) { throw "AVD metadata is incomplete for $avdName." }
    $configText = Get-Content -Raw $avdConfig
    if ($configText -notmatch '(?m)^image\.sysdir\.1=system-images\\android-37\.0\\google_apis_playstore\\x86_64\\?$' -or
        $configText -notmatch '(?m)^hw\.device\.name=pixel_7$') {
        throw "Existing $avdName is not the expected Android 37 Google Play Pixel 7 AVD; refusing to modify or launch it."
    }
    if ($configText -notmatch '(?m)^hw\.initialOrientation=portrait$') {
        throw "The $avdName AVD is not configured for portrait orientation."
    }
    $runningInstances = Get-CimInstance Win32_Process -Filter "Name = 'emulator.exe'" -ErrorAction SilentlyContinue
    if ($runningInstances | Where-Object { $_.CommandLine -match '(?i)(^|\s)-avd\s+"?GutCare_API_37("|\s|$)' }) {
        throw "$avdName is already running outside this harness; refusing to attach or stop it."
    }

    New-Item -ItemType Directory -Force -Path $evidenceDir | Out-Null
    $env:ANDROID_SDK_ROOT = $sdkRoot
    $env:ANDROID_HOME = $sdkRoot
    $env:ANDROID_ADB_SERVER_PORT = [string]$adbPort
    & $adbExe start-server | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the isolated adb server.' }
    $startedAdbServer = $true

    $emulatorProcess = Start-Process -FilePath $emulatorExe -ArgumentList @(
        '-avd', $avdName,
        '-port', [string]$emulatorPort,
        '-no-snapshot',
        '-wipe-data',
        '-no-boot-anim',
        '-gpu', 'auto'
    ) -PassThru -WindowStyle Hidden

    $deadline = (Get-Date).AddMinutes(5)
    $deviceReady = $false
    while ((Get-Date) -lt $deadline) {
        if ($emulatorProcess.HasExited) { throw "Emulator exited early with code $($emulatorProcess.ExitCode). Check hardware acceleration and emulator diagnostics." }
        $devices = & $adbExe devices
        if ($LASTEXITCODE -ne 0) { throw 'Isolated adb server stopped responding.' }
        if ($devices -match [regex]::Escape("$serial`tdevice")) {
            $reportedAvd = Get-AvdNameForSerial $serial
            if ($reportedAvd -ne $avdName -or -not (Test-LaunchedEmulatorIdentity)) {
                throw "Serial $serial did not match the process launched by this harness and the expected AVD name."
            }
            $boot = & $adbExe -s $serial shell getprop sys.boot_completed 2>$null
            if ($LASTEXITCODE -eq 0 -and ([string]$boot).Trim() -eq '1') {
                $deviceReady = $true
                break
            }
        }
        Start-Sleep -Seconds 3
    }
    if (-not $deviceReady) { throw 'Android 37 AVD did not finish booting within 5 minutes.' }

    $actualLocale = ''
    $maxLocaleAttempts = 3
    for ($localeAttempt = 1; $localeAttempt -le $maxLocaleAttempts; $localeAttempt++) {
        $localeSettleDeadline = (Get-Date).AddSeconds(30)
        $settingsServiceReady = $false
        while ((Get-Date) -lt $localeSettleDeadline) {
            $localeReadOutput = & $adbExe -s $serial shell settings get system system_locales 2>&1
            $localeReadExitCode = $LASTEXITCODE
            $localeReadText = ([string]($localeReadOutput | Out-String)).Trim()
            $localeProperty = (& $adbExe -s $serial shell getprop persist.sys.locale 2>$null | Out-String).Trim()
            if ($localeReadExitCode -eq 0 -and $localeReadText -notmatch "Can't find service: settings") {
                $settingsServiceReady = $true
                $localeSetting = $localeReadText
                if ($localeSetting -eq 'zh-CN') { $actualLocale = $localeSetting; break }
            }
            Start-Sleep -Seconds 2
        }
        if ($actualLocale -eq 'zh-CN') { break }
        if ($localeAttempt -eq $maxLocaleAttempts) { break }

        if (-not $settingsServiceReady) {
            throw "Android settings service did not become available within 30 seconds (last output='$localeReadText')."
        }

        # Re-read immediately before writing: a successful earlier probe may have
        # raced a service restart while the locale was settling.
        $settingsReadyDeadline = (Get-Date).AddSeconds(30)
        $settingsServiceReady = $false
        while ((Get-Date) -lt $settingsReadyDeadline) {
            $localeReadOutput = & $adbExe -s $serial shell settings get system system_locales 2>&1
            $localeReadExitCode = $LASTEXITCODE
            $localeReadText = ([string]($localeReadOutput | Out-String)).Trim()
            if ($localeReadExitCode -eq 0 -and $localeReadText -notmatch "Can't find service: settings") {
                $settingsServiceReady = $true
                $localeSetting = $localeReadText
                break
            }
            Start-Sleep -Seconds 2
        }
        if (-not $settingsServiceReady) {
            throw "Android settings service was unavailable before locale update (last output='$localeReadText')."
        }

        & $adbExe -s $serial shell settings put system system_locales zh-CN | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not reapply zh-CN system locale on attempt $localeAttempt." }
        $localeSetting = (& $adbExe -s $serial shell settings get system system_locales 2>$null | Out-String).Trim()
        if ($localeSetting -ne 'zh-CN') { continue }

        & $adbExe -s $serial reboot | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "The AVD could not reboot for locale attempt $localeAttempt." }
        $localeBootDeadline = (Get-Date).AddMinutes(3)
        $localeBooted = $false
        while ((Get-Date) -lt $localeBootDeadline) {
            $devices = & $adbExe devices
            if ($devices -match [regex]::Escape("$serial`tdevice")) {
                $boot = & $adbExe -s $serial shell getprop sys.boot_completed 2>$null
                if ($LASTEXITCODE -eq 0 -and ([string]$boot).Trim() -eq '1') { $localeBooted = $true; break }
            }
            Start-Sleep -Seconds 3
        }
        if (-not $localeBooted) { throw "The AVD did not finish rebooting for locale attempt $localeAttempt." }
    }
    if ($actualLocale -ne 'zh-CN') { throw "System locale did not stabilize at zh-CN after $maxLocaleAttempts attempts (settings='$localeSetting', property='$localeProperty')." }

    Invoke-PrivateAdb -s $serial shell settings put system accelerometer_rotation 0
    Invoke-PrivateAdb -s $serial shell settings put system user_rotation 0
    Invoke-PrivateAdb -s $serial shell settings put system font_scale 1.0
    $actualFontScale = (& $adbExe -s $serial shell settings get system font_scale 2>$null | Out-String).Trim()
    if ($actualFontScale -ne '1.0') { throw "The AVD font scale is '$actualFontScale', expected 1.0." }

    $frameworkReadyDeadline = (Get-Date).AddSeconds(90)
    $frameworkReady = $false
    $packageServiceOutput = ''
    $activityServiceOutput = ''
    $packageProbeOutput = ''
    while ((Get-Date) -lt $frameworkReadyDeadline) {
        if ($emulatorProcess.HasExited) { throw "Emulator exited while waiting for Android framework readiness (code $($emulatorProcess.ExitCode))." }

        $packageServiceOutput = (& $adbExe -s $serial shell service check package 2>&1 | Out-String).Trim()
        $packageServiceExitCode = $LASTEXITCODE
        $activityServiceOutput = (& $adbExe -s $serial shell service check activity 2>&1 | Out-String).Trim()
        $activityServiceExitCode = $LASTEXITCODE
        $packageProbeOutput = (& $adbExe -s $serial shell pm list packages --user 0 android 2>&1 | Out-String).Trim()
        $packageProbeExitCode = $LASTEXITCODE

        if ($packageServiceExitCode -eq 0 -and $packageServiceOutput -match 'Service package: found' -and
            $activityServiceExitCode -eq 0 -and $activityServiceOutput -match 'Service activity: found' -and
            $packageProbeExitCode -eq 0 -and $packageProbeOutput -match '(?m)^package:android$') {
            $frameworkReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $frameworkReady) {
        throw "Android framework/package manager did not stabilize within 90 seconds (package='$packageServiceOutput'; activity='$activityServiceOutput'; probe='$packageProbeOutput')."
    }

    $existingMappings = @(& subst)
    foreach ($letter in 'Z'..'D') {
        if ((Get-PSDrive -Name $letter -ErrorAction SilentlyContinue) -or ($existingMappings | Where-Object { $_ -match "^${letter}:\\: => " })) { continue }
        $mappedDrive = "${letter}:"
        break
    }
    if (-not $mappedDrive) { throw 'No unused drive letter is available for an ASCII Gradle path.' }
    subst $mappedDrive $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the temporary ASCII drive mapping for Gradle.' }
    $mappedByThisScript = $true
    $sourceSettings = Join-Path $androidRoot 'settings.gradle.kts'
    $mappedAndroidRoot = Join-Path "$mappedDrive\" 'android'
    $mappedSettings = Join-Path $mappedAndroidRoot 'settings.gradle.kts'
    if (-not (Test-Path $mappedSettings)) { throw 'The temporary drive mapping does not expose the expected Android project file.' }
    $sourceSettingsInfo = Get-Item -LiteralPath $sourceSettings
    $mappedSettingsInfo = Get-Item -LiteralPath $mappedSettings
    $sourceSettingsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceSettings).Hash
    $mappedSettingsHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $mappedSettings).Hash
    if ($sourceSettingsInfo.Length -ne $mappedSettingsInfo.Length -or $sourceSettingsHash -ne $mappedSettingsHash) {
        throw 'The temporary drive mapping does not resolve to this repository; refusing to run Gradle.'
    }

    $testStartedAt = Get-Date
    Push-Location $mappedAndroidRoot
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $apkPath = Join-Path $androidRoot 'app\build\outputs\apk\debug\app-debug.apk'
        $gradleOutput = & '.\gradlew.bat' connectedDebugAndroidTest --no-daemon --max-workers=1 2>&1
        $testExitCode = $LASTEXITCODE
        if (-not (Test-Path $apkPath)) { throw 'connectedDebugAndroidTest did not produce the debug APK.' }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }

    $resultDir = Join-Path $androidRoot 'app\build\outputs\androidTest-results\connected\debug'
    $xmlFiles = @(Get-ChildItem $resultDir -Filter '*.xml' -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -ge $testStartedAt })
    foreach ($xmlFile in $xmlFiles) {
        try {
            [xml]$xml = Get-Content -Raw $xmlFile.FullName
            foreach ($suite in @($xml.SelectNodes('//testsuite'))) {
                $testCount += [int]$suite.tests
                $failureCount += [int]$suite.failures
                $errorCount += [int]$suite.errors
            }
        }
        catch { }
    }
    $status = if ($testExitCode -eq 0 -and $testCount -gt 0 -and $failureCount -eq 0 -and $errorCount -eq 0) { 'passed' } else { 'failed' }

    if ((Get-AvdNameForSerial $serial) -ne $avdName -or -not (Test-LaunchedEmulatorIdentity)) {
        throw "Device identity changed before screenshot capture; refusing to capture from $serial."
    }
    & $adbExe -s $serial install -r $apkPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not reinstall the debug APK after instrumentation cleanup.' }
    $installedPackageOutput = (& $adbExe -s $serial shell pm list packages com.gutcare.app 2>&1 | Out-String).Trim()
    $resolvedActivityOutput = (& $adbExe -s $serial shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER com.gutcare.app 2>&1 | Out-String).Trim()
    [ordered]@{
        package_list = $installedPackageOutput
        resolved_launcher_activity = $resolvedActivityOutput
    } | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 (Join-Path $evidenceDir 'launch-diagnostics.json')
    if ($installedPackageOutput -notmatch 'package:com\.gutcare\.app') { throw "GutCare package is not installed: $installedPackageOutput" }
    if ($resolvedActivityOutput -notmatch 'com\.gutcare\.app/.?MainActivity|com\.gutcare\.app/com\.gutcare\.app\.MainActivity') {
        throw "Could not resolve the GutCare launcher activity: $resolvedActivityOutput"
    }
    & $adbExe -s $serial shell am force-stop com.gutcare.app | Out-Null
    $activityLaunchOutput = (& $adbExe -s $serial shell am start -W -n com.gutcare.app/com.gutcare.app.MainActivity 2>&1 | Out-String).Trim()
    $activityLaunchExitCode = $LASTEXITCODE
    [ordered]@{
        package_list = $installedPackageOutput
        resolved_launcher_activity = $resolvedActivityOutput
        activity_launch_exit_code = $activityLaunchExitCode
        activity_launch_output = $activityLaunchOutput
    } | ConvertTo-Json -Depth 3 | Set-Content -Encoding utf8 (Join-Path $evidenceDir 'launch-diagnostics.json')
    if ($activityLaunchExitCode -ne 0) { throw "GutCare MainActivity launch failed (exit=$activityLaunchExitCode): $activityLaunchOutput" }
    $foregroundLine = ''
    $foregroundDeadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $foregroundDeadline) {
        $activityDump = & $adbExe -s $serial shell dumpsys activity activities 2>$null
        $candidateLine = [string](($activityDump | Select-String -Pattern 'mResumedActivity|topResumedActivity' | Select-Object -First 1).Line)
        if ($candidateLine -match 'com\.gutcare\.app/') { $foregroundLine = $candidateLine; break }
        Start-Sleep -Seconds 2
    }
    if (-not $foregroundLine) { throw 'The foreground activity is not a GutCare activity; refusing to save a screenshot.' }
    $foregroundMatch = [regex]::Match($foregroundLine, 'com\.gutcare\.app/[^}\s]+')
    if (-not $foregroundMatch.Success) { throw 'Could not identify the foreground GutCare activity.' }
    $foregroundActivity = $foregroundMatch.Value
    Start-Sleep -Seconds 2

    $deviceScreenshot = '/sdcard/gutcare-emulator-verify.png'
    & $adbExe -s $serial shell screencap -p $deviceScreenshot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Screenshot capture on the verified AVD failed.' }
    & $adbExe -s $serial pull $deviceScreenshot $screenshotPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Screenshot collection from the verified AVD failed.' }
    & $adbExe -s $serial shell rm $deviceScreenshot | Out-Null
    if (-not (Test-Path $screenshotPath) -or (Get-Item $screenshotPath).Length -eq 0) { throw 'Screenshot capture failed.' }

    $summary = [ordered]@{
        run_id = $runId
        status = $status
        device = $avdName
        serial = $serial
        android_api = '37'
        image = 'google_apis_playstore;x86_64'
        orientation = 'portrait'
        actual_locale = $actualLocale
        locale_attempts = $localeAttempt
        font_scale = $actualFontScale
        foreground_package = 'com.gutcare.app'
        foreground_activity = $foregroundActivity
        connected_debug_android_test_exit_code = $testExitCode
        tests = $testCount
        failures = $failureCount
        errors = $errorCount
        screenshot = $screenshotPath
        gradle_reports = (Join-Path $androidRoot 'app\build\reports\androidTests\connected\debug')
    }
    $summary | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $summaryPath
    Write-Output ($summary | ConvertTo-Json -Depth 4)
}
catch {
    $status = 'failed'
    $safeFailure = ([string]$_.Exception.Message -replace [regex]::Escape($androidRoot), '<android-project>' -replace '[A-Za-z]:\\[^\s]+' , '<path>')
    [Console]::Error.WriteLine($safeFailure)
    if (Test-Path $evidenceDir) {
        $failureSummary = [ordered]@{
            run_id = $runId
            status = $status
            device = $avdName
            serial = $serial
            tests = $testCount
            failures = $failureCount
            errors = $errorCount
            actual_locale = if ($actualLocale) { $actualLocale } else { $null }
            locale_attempts = $localeAttempt
            locale_settings = $localeSetting
            locale_property = $localeProperty
            foreground_package = if ($foregroundActivity) { 'com.gutcare.app' } else { $null }
            foreground_activity = if ($foregroundActivity) { $foregroundActivity } else { $null }
            installed_package_output = $installedPackageOutput
            resolved_activity_output = $resolvedActivityOutput
            activity_launch_output = $activityLaunchOutput
            failure = $safeFailure
            screenshot = if (Test-Path $screenshotPath) { $screenshotPath } else { $null }
        }
        $failureSummary | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $summaryPath
    }
}
finally {
    if ($mappedByThisScript) {
        subst $mappedDrive /D | Out-Null
    }
    if ($emulatorProcess -and -not $emulatorProcess.HasExited -and (Test-LaunchedEmulatorIdentity)) {
        $reportedAvd = Get-AvdNameForSerial $serial
        if ($reportedAvd -eq $avdName) {
            & $adbExe -s $serial emu kill 2>$null | Out-Null
            $emulatorProcess.WaitForExit(15000) | Out-Null
            if (-not $emulatorProcess.HasExited -and (Test-LaunchedEmulatorIdentity)) {
                Stop-Process -Id $emulatorProcess.Id -ErrorAction SilentlyContinue
            }
        }
    }
    if ($startedAdbServer) {
        & $adbExe kill-server 2>$null | Out-Null
    }
    if ($null -eq $previousAdbPort) { Remove-Item Env:ANDROID_ADB_SERVER_PORT -ErrorAction SilentlyContinue }
    else { $env:ANDROID_ADB_SERVER_PORT = $previousAdbPort }
    if ($null -eq $previousSdkRoot) { Remove-Item Env:ANDROID_SDK_ROOT -ErrorAction SilentlyContinue }
    else { $env:ANDROID_SDK_ROOT = $previousSdkRoot }
    if ($null -eq $previousAndroidHome) { Remove-Item Env:ANDROID_HOME -ErrorAction SilentlyContinue }
    else { $env:ANDROID_HOME = $previousAndroidHome }
}

if ($status -ne 'passed') { exit 1 }
