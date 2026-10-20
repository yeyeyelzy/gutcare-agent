[CmdletBinding()]
param(
    [string]$Serial,
    [string]$AvdName = 'GutCare_API_37',
    [ValidateRange(1, 65535)] [int]$AdbServerPort = 5037
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$androidRoot = Join-Path $root 'android'
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
$sdkRoot = 'D:\Android\Sdk'
$adb = Join-Path $sdkRoot 'platform-tools\adb.exe'
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$evidenceDir = Join-Path $androidRoot "build\emulator-evidence\phone-demo-records-$runId"
$summaryPath = Join-Path $evidenceDir 'summary.json'
$diagnosticPath = Join-Path $evidenceDir 'diagnostic.json'
$mappedDrive = $null
$mutex = [System.Threading.Mutex]::new($false, 'Local\GutCarePhoneDemoAndroidAuth')
$lockAcquired = $false
$status = 'failed'
$stage = 'preflight'

function Write-SafeSummary([string]$Result, [string]$CurrentStage) {
    $summary = [ordered]@{
        schema_version = '1.0'
        test_id = 'ANDROID-F03-F04-F05-F14-LIVE'
        status = $Result
        stage = $CurrentStage
        environment = 'preexisting local phone-demo Docker Compose; Android emulator bridge 10.0.2.2'
        api_base = 'http://10.0.2.2:8000/api/v1/'
        emulator_serial = $Serial
        adb_server_port = $AdbServerPort
        executed_at = (Get-Date).ToUniversalTime().ToString('o')
        scenarios = @('diet CRUD', 'stool CRUD', 'symptom CRUD/status history', 'mood consent/CRUD', '409 stale version', 'cursor pagination', '401 after logout/session clear')
        secrets_recorded = $false
        response_bodies_recorded = $false
        diagnostic_file = 'diagnostic.json'
    }
    [System.IO.Directory]::CreateDirectory($evidenceDir) | Out-Null
    [System.IO.File]::WriteAllText($summaryPath, ($summary | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
}

function Write-SafeDiagnostic([string]$Output) {
    $safe = [ordered]@{ test_id = 'ANDROID-F03-F04-F05-F14-LIVE'; failure = 'Unclassified live instrumentation failure.' }
    $stack = [regex]::Match($Output, '(?m)^INSTRUMENTATION_STATUS: stack=(?<stack>[^\r\n]+)')
    if ($stack.Success) {
        $match = [regex]::Match($stack.Groups['stack'].Value, '^(?:java\.lang\.[\w.]+: )?(?<stage>[a-z]+(?:/[a-z0-9_-]+)+) failed: status=(?<status>\d{3}|none) code=(?<code>[A-Z0-9_]+|none)(?: request_id=(?<requestId>[0-9a-fA-F-]{36}))?$')
        if ($match.Success) {
            $safe = [ordered]@{
                test_id = 'ANDROID-F03-F04-F05-F14-LIVE'
                stage = $match.Groups['stage'].Value
                status = $match.Groups['status'].Value
                code = $match.Groups['code'].Value
                request_id = if ($match.Groups['requestId'].Success) { $match.Groups['requestId'].Value } else { $null }
            }
        } elseif ($stack.Groups['stack'].Value -match 'Moshi|JsonDataException|JsonEncodingException') {
            $safe = [ordered]@{ test_id = 'ANDROID-F03-F04-F05-F14-LIVE'; failure = 'DTO response parsing failed; body suppressed.' }
        }
    }
    [System.IO.Directory]::CreateDirectory($evidenceDir) | Out-Null
    [System.IO.File]::WriteAllText($diagnosticPath, ($safe | ConvertTo-Json -Depth 4), [System.Text.UTF8Encoding]::new($false))
}

try {
    $lockAcquired = $mutex.WaitOne(0)
    if (-not $lockAcquired) { throw 'Another phone-demo Android live test is active.' }
    foreach ($required in @($composeFile, $envFile, $adb, (Join-Path $androidRoot 'settings.gradle.kts'))) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required local test dependency is missing: $required" }
    }
    $stage = 'phone-demo-readiness'
    $containers = @(& docker ps -q --filter 'label=com.docker.compose.project=gutcare-phone-demo')
    if ($LASTEXITCODE -ne 0 -or $containers.Count -lt 4) { throw 'The isolated phone-demo Compose project is not fully running.' }
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health/ready' -TimeoutSec 10
    if ($health.StatusCode -ne 200) { throw 'Phone-demo readiness did not return HTTP 200.' }

    $stage = 'emulator-selection'
    $deviceLines = @(& $adb -P $AdbServerPort devices)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to enumerate Android emulator devices.' }
    $emulators = @($deviceLines | ForEach-Object { if ($_ -match '^(emulator-\d+)\s+device$') { $Matches[1] } })
    if ($Serial) {
        if ($Serial -notmatch '^emulator-\d+$' -or $Serial -notin $emulators) { throw 'The requested emulator serial is not connected.' }
    } elseif ($emulators.Count -eq 1) {
        $Serial = $emulators[0]
    } else {
        throw 'Exactly one emulator must be connected, or pass -Serial emulator-NNNN.'
    }
    $identity = (& $adb -P $AdbServerPort -s $Serial get-serialno | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $identity -cne $Serial) { throw 'The selected emulator serial could not be verified on the requested ADB server.' }
    $api = (& $adb -P $AdbServerPort -s $Serial shell getprop ro.build.version.sdk | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $api -ne '37') { throw "The selected emulator must run Android API 37 (reported '$api')." }
    $avdOutput = @(& $adb -P $AdbServerPort -s $Serial emu avd name 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to verify the selected emulator AVD name.' }
    $actualAvdName = ($avdOutput | Where-Object { $_ -and $_ -notmatch '^OK$' } | Select-Object -First 1 | Out-String).Trim()
    if ($actualAvdName -cne $AvdName) { throw "The selected emulator must use AVD '$AvdName' (reported '$actualAvdName')." }

    $stage = 'android-build'
    $repoPath = (Resolve-Path $root).Path
    $existingMappings = @(& subst)
    foreach ($letter in @('S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z')) {
        if ((Get-PSDrive -Name $letter -ErrorAction SilentlyContinue) -or ($existingMappings | Where-Object { $_ -match "^${letter}:\\: => " })) { continue }
        $mappedDrive = "${letter}:"
        break
    }
    if (-not $mappedDrive) { throw 'No unused ASCII drive letter is available for Gradle.' }
    & subst $mappedDrive $repoPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the temporary ASCII drive mapping.' }
    Push-Location (Join-Path "$mappedDrive\" 'android')
    try {
        & '.\gradlew.bat' :app:assembleDebug :app:assembleDebugAndroidTest --no-daemon --max-workers=1 '-PdebugApiBaseUrl=http://10.0.2.2:8000/api/v1/'
        if ($LASTEXITCODE -ne 0) { throw 'Android live-test APK build failed.' }
    } finally { Pop-Location }

    $stage = 'apk-install'
    $appApk = Join-Path $androidRoot 'app\build\outputs\apk\debug\app-debug.apk'
    $testApk = Join-Path $androidRoot 'app\build\outputs\apk\androidTest\debug\app-debug-androidTest.apk'
    foreach ($apk in @($appApk, $testApk)) {
        if (-not (Test-Path -LiteralPath $apk -PathType Leaf)) { throw "Expected APK is missing: $apk" }
        & $adb -P $AdbServerPort -s $Serial install -r $apk | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'APK installation failed.' }
    }

    $stage = 'live-contract'
    $instrumentation = @(& $adb -P $AdbServerPort -s $Serial shell am instrument -w -r `
        -e phoneDemoRecordsLive true `
        -e class com.gutcare.app.core.network.PhoneDemoRecordsLiveContractTest `
        com.gutcare.app.test/androidx.test.runner.AndroidJUnitRunner 2>&1)
    $instrumentationExit = $LASTEXITCODE
    $safeOutput = ($instrumentation | Out-String)
    if ($instrumentationExit -ne 0 -or $safeOutput -notmatch '(?m)^OK \(1 test\)\s*$' -or $safeOutput -match '(?m)^FAILURES!!!') {
        Write-SafeDiagnostic $safeOutput
        throw 'Android records live contract failed; inspect transient instrumentation output locally.'
    }

    $status = 'passed'
    Write-SafeSummary $status 'complete'
    Write-Host "Phone-demo Android records live contract passed. Safe evidence: $summaryPath"
} catch {
    Write-SafeSummary 'failed' $stage
    throw
} finally {
    if ($mappedDrive) { subst $mappedDrive /D | Out-Null }
    if ($lockAcquired) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
