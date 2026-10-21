[CmdletBinding()]
param([string]$SdkRoot)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sdkRoot = if ($SdkRoot) { $SdkRoot } elseif ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
$adbPort = 5038
$emulatorPort = 5580
$serial = "emulator-$emulatorPort"
$avdName = 'GutCare_API_37'
$avdDir = Join-Path $env:USERPROFILE ".android\avd\$avdName.avd"
$avdConfig = Join-Path $avdDir 'config.ini'
$avdIni = Join-Path $env:USERPROFILE ".android\avd\$avdName.ini"
$adbExe = Join-Path $sdkRoot 'platform-tools\adb.exe'
$emulatorExe = Join-Path $sdkRoot 'emulator\emulator.exe'
$systemImage = Join-Path $sdkRoot 'system-images\android-37.0\google_apis_playstore\x86_64\system.img'
$evidenceRoot = Join-Path $root 'android\build\emulator-evidence'
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$evidenceDir = Join-Path $evidenceRoot "phone-demo-auth-startup-$runId"
$startupSummaryPath = Join-Path $evidenceDir 'startup-summary.json'
$emulatorProcess = $null
$startedAdbServer = $false
$currentStage = 'initialization'
$startupStatus = 'running'
$startupFailure = $null
$authInvoked = $false
$startupEvents = [System.Collections.Generic.List[object]]::new()
$null = New-Item -ItemType Directory -Force -Path $evidenceDir
$previousAdbPort = $env:ANDROID_ADB_SERVER_PORT
$previousSdkRoot = $env:ANDROID_SDK_ROOT
$previousAndroidHome = $env:ANDROID_HOME
$previousPath = $env:PATH

function Test-TcpPortFree([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch { return $false }
    finally { if ($listener) { $listener.Stop() } }
}

function Test-LaunchedEmulatorIdentity {
    if (-not $script:emulatorProcess) { return $false }
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $($script:emulatorProcess.Id)" -ErrorAction SilentlyContinue
    return ($processInfo -and $processInfo.Name -eq 'emulator.exe' -and $processInfo.CommandLine -match '(?i)(^|\s)-avd\s+"?GutCare_API_37("|\s|$)')
}

function Get-AvdNameForSerial {
    $output = & $script:adbExe -s $script:serial emu avd name 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) { return $null }
    return ([string]$output[0]).Trim()
}

function Save-StartupEvidence {
    $document = [ordered]@{
        schema_version = '1.0'
        run_id = $runId
        status = $startupStatus
        stage = $currentStage
        auth_invoked = $authInvoked
        events = @($startupEvents.ToArray())
        failure = $startupFailure
    }
    [System.IO.File]::WriteAllText(
        $startupSummaryPath,
        ($document | ConvertTo-Json -Depth 6),
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Add-StartupEvent([string]$Stage, [string]$Status, [string]$Detail = '') {
    $script:currentStage = $Stage
    $entry = [ordered]@{ stage = $Stage; status = $Status; at = (Get-Date).ToUniversalTime().ToString('o') }
    if ($Detail) { $entry.detail = $Detail }
    $script:startupEvents.Add($entry)
    Save-StartupEvidence
}

function Get-SafeExceptionMessage([string]$Message) {
    $safe = $Message
    $safe = $safe -replace '(?i)(password|token|secret|authorization|receipt|email)(\s*[:=]\s*)[^,\s;]+', '$1$2<redacted>'
    $safe = $safe -replace '(?i)\bBearer\s+\S+', 'Bearer <redacted>'
    $safe = $safe -replace '(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', '<email>'
    $safe = $safe -replace '(?i)(postgres(?:ql)?(?:\+[^:]*)?://)[^\s]+', '$1<redacted>'
    $safe = $safe -replace '[A-Za-z]:\\[^\s"''<>]+', '<path>'
    $safe = $safe -replace '\s+', ' '
    if ($safe.Length -gt 240) { $safe = $safe.Substring(0, 240) }
    return $safe
}

try {
    Add-StartupEvent 'component_check' 'started'
    foreach ($path in @($adbExe, $emulatorExe, $systemImage, $avdConfig)) {
        if (-not (Test-Path -LiteralPath $path)) { throw "Required emulator component not found: $path" }
    }
    if (-not (Test-Path -LiteralPath $avdIni)) { throw 'GutCare_API_37 AVD metadata file is missing.' }
    $configText = Get-Content -Raw -LiteralPath $avdConfig
    if ($configText -notmatch '(?m)^image\.sysdir\.1=system-images\\android-37\.0\\google_apis_playstore\\x86_64\\?$' -or
        $configText -notmatch '(?m)^hw\.device\.name=pixel_7$' -or
        $configText -notmatch '(?m)^hw\.initialOrientation=portrait$') {
        throw 'GutCare_API_37 does not match the Android 37 Google Play Pixel 7 portrait configuration.'
    }
    $avdIniText = Get-Content -Raw -LiteralPath $avdIni
    if ($avdIniText -notmatch '(?m)^path\.rel=avd\\GutCare_API_37\.avd\s*$' -and
        $avdIniText -notmatch '(?m)^path=.*GutCare_API_37\.avd\s*$') {
        throw 'GutCare_API_37 AVD pointer does not resolve to its expected AVD directory.'
    }
    if (Get-CimInstance Win32_Process -Filter "Name = 'emulator.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match '(?i)(^|\s)-avd\s+"?GutCare_API_37("|\s|$)' }) {
        throw 'GutCare_API_37 is already running outside this wrapper; refusing to attach or stop it.'
    }
    Add-StartupEvent 'component_check' 'passed' 'sdk_and_avd_components_present'

    Add-StartupEvent 'port_check' 'started'
    foreach ($port in @($adbPort, $emulatorPort, ($emulatorPort + 1))) {
        if (-not (Test-TcpPortFree $port)) { throw "Required private emulator port $port is already in use." }
    }
    Add-StartupEvent 'port_check' 'passed' '5038_5580_5581_available'

    Add-StartupEvent 'service_check' 'started'
    # Verify both liveness and readiness before starting the emulator or auth requests.
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health/live' -Method Get -TimeoutSec 5
    if ($health.StatusCode -ne 200) { throw 'phone-demo health/live did not return HTTP 200.' }
    $readiness = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health/ready' -Method Get -TimeoutSec 5
    if ($readiness.StatusCode -ne 200 -or $readiness.Content -notmatch '"status"\s*:\s*"ready"') {
        throw 'phone-demo health/ready did not return HTTP 200 and ready.'
    }
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) { throw 'Docker CLI is required to verify phone-demo services.' }
    $containerIds = @(& $docker.Source ps -aq --no-trunc --filter 'label=com.docker.compose.project=gutcare-phone-demo')
    if ($LASTEXITCODE -ne 0 -or $containerIds.Count -eq 0) { throw 'Could not verify the existing phone-demo Compose services.' }
    $ignoredOptionalStopped = [System.Collections.Generic.List[string]]::new()
    foreach ($id in $containerIds) {
        $state = [string](& $docker.Source inspect --format '{{.State.Status}}|{{.State.ExitCode}}|{{ index .Config.Labels "com.docker.compose.service" }}' $id)
        if ($LASTEXITCODE -ne 0) { throw 'Could not inspect phone-demo Compose service state.' }
        $parts = $state.Trim().Split('|', 3)
        if ($parts.Count -ne 3) { throw 'Could not parse phone-demo Compose service state.' }
        $status = $parts[0]
        $exitCode = $parts[1]
        $service = $parts[2]
        if ($status -eq 'running' -and $exitCode -eq '0') { continue }
        if ($service -eq 'minio-init' -and $status -eq 'exited' -and $exitCode -eq '0') { continue }
        if ($service -in @('agent', 'analysis-dispatcher') -and $status -eq 'exited' -and $exitCode -in @('0', '137')) {
            $ignoredOptionalStopped.Add($service)
            continue
        }
        throw 'A required phone-demo Compose service is not ready; no auth request was sent.'
    }
    $ignored = if ($ignoredOptionalStopped.Count -gt 0) { ';ignored_optional_stopped=' + (($ignoredOptionalStopped | Sort-Object -Unique) -join ',') } else { ';ignored_optional_stopped=none' }
    Add-StartupEvent 'service_check' 'passed' ("containers=" + $containerIds.Count + ';only_successful_minio_init_may_be_exited' + $ignored)

    Add-StartupEvent 'adb_start' 'started'
    $env:ANDROID_SDK_ROOT = $sdkRoot
    $env:ANDROID_HOME = $sdkRoot
    $env:ANDROID_ADB_SERVER_PORT = [string]$adbPort
    $env:PATH = (Join-Path $sdkRoot 'platform-tools') + ';' + $previousPath
    & $adbExe start-server | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the isolated adb server on port 5038.' }
    $startedAdbServer = $true
    Add-StartupEvent 'adb_start' 'passed' 'private_adb_port_5038'

    Add-StartupEvent 'emulator_start' 'started'
    $emulatorProcess = Start-Process -FilePath $emulatorExe -ArgumentList @(
        '-avd', $avdName,
        '-port', [string]$emulatorPort,
        '-no-snapshot',
        '-wipe-data',
        '-no-boot-anim',
        '-gpu', 'auto'
    ) -PassThru -WindowStyle Hidden
    Add-StartupEvent 'emulator_start' 'passed' 'avd=GutCare_API_37;console_port=5580'
    Add-StartupEvent 'boot_wait' 'started'
    $deadline = (Get-Date).AddMinutes(5)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($emulatorProcess.HasExited) { throw "Emulator exited before boot completed (code $($emulatorProcess.ExitCode))." }
        $devices = & $adbExe devices
        if ($LASTEXITCODE -ne 0) { throw 'Isolated adb server stopped responding.' }
        if ($devices -match [regex]::Escape("$serial`tdevice")) {
            if ((Get-AvdNameForSerial) -ne $avdName -or -not (Test-LaunchedEmulatorIdentity)) {
                throw "Serial $serial did not match the emulator launched by this wrapper."
            }
            $boot = & $adbExe -s $serial shell getprop sys.boot_completed 2>$null
            if ($LASTEXITCODE -eq 0 -and ([string]$boot).Trim() -eq '1') { $ready = $true; break }
        }
        Start-Sleep -Seconds 3
    }
    if (-not $ready) { throw 'Android 37 emulator did not finish booting within 5 minutes; auth was not run.' }

    Add-StartupEvent 'boot_wait' 'passed' 'sys_boot_completed=1;avd_identity_verified'
    Add-StartupEvent 'auth_gate' 'started'
    $authInvoked = $true
    Save-StartupEvidence
    & (Join-Path $PSScriptRoot 'test-phone-demo-android-auth.ps1') -Serial $serial
    if ($LASTEXITCODE -ne 0) { throw 'Phone-demo Android auth gate failed.' }
    Add-StartupEvent 'auth_gate' 'passed' 'wrapper_received_success_exit'
    $startupStatus = 'passed'
    Save-StartupEvidence
} catch {
    $startupStatus = 'failed'
    $startupFailure = [ordered]@{
        exception_type = $_.Exception.GetType().FullName
        message = Get-SafeExceptionMessage ([string]$_.Exception.Message)
    }
    Add-StartupEvent $currentStage 'failed'
    Save-StartupEvidence
    throw "Android auth emulator wrapper failed at stage '$currentStage'; safe diagnostics: $startupSummaryPath"
} finally {
    if ($emulatorProcess -and -not $emulatorProcess.HasExited -and (Test-LaunchedEmulatorIdentity) -and (Get-AvdNameForSerial) -eq $avdName) {
        & $adbExe -s $serial emu kill 2>$null | Out-Null
        $emulatorProcess.WaitForExit(15000) | Out-Null
        if (-not $emulatorProcess.HasExited -and (Test-LaunchedEmulatorIdentity)) { Stop-Process -Id $emulatorProcess.Id -ErrorAction SilentlyContinue }
    }
    if ($startedAdbServer) { & $adbExe kill-server 2>$null | Out-Null }
    if ($null -eq $previousAdbPort) { Remove-Item Env:ANDROID_ADB_SERVER_PORT -ErrorAction SilentlyContinue } else { $env:ANDROID_ADB_SERVER_PORT = $previousAdbPort }
    if ($null -eq $previousSdkRoot) { Remove-Item Env:ANDROID_SDK_ROOT -ErrorAction SilentlyContinue } else { $env:ANDROID_SDK_ROOT = $previousSdkRoot }
    if ($null -eq $previousAndroidHome) { Remove-Item Env:ANDROID_HOME -ErrorAction SilentlyContinue } else { $env:ANDROID_HOME = $previousAndroidHome }
    $env:PATH = $previousPath
    Save-StartupEvidence
}
