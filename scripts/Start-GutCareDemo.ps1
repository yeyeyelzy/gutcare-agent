[CmdletBinding()]
param(
    [ValidateRange(30, 600)]
    [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$root = if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'compose.phone-demo.yaml') -PathType Leaf) {
    $PSScriptRoot
} else {
    Split-Path -Parent $PSScriptRoot
}
$composeProject = 'gutcare-competition-demo'
$requiredFiles = @(
    'compose.phone-demo.yaml',
    'android\app-debug.apk',
    'scripts\phone-demo-agent-up.ps1',
    'scripts\phone-demo-down.ps1'
)
foreach ($relativePath in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relativePath) -PathType Leaf)) {
        throw "Package is incomplete: required file is missing: $relativePath"
    }
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    throw 'Docker CLI is unavailable. Install and start Docker Desktop, then run this script again.'
}
$null = & $docker.Source compose version 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Compose v2 is unavailable. Update or start Docker Desktop, then run this script again.'
}
$null = & $docker.Source info --format '{{.ServerVersion}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Docker Desktop is not ready. Start Docker Desktop and wait for its engine before retrying.'
}

# This launcher is deliberately mock-only. Refuse local live settings instead
# of allowing a package launch to send data to an external model.
$localAgentEnv = Join-Path $root '.env.agent.local'
if (Test-Path -LiteralPath $localAgentEnv -PathType Leaf) {
    $settings = @{}
    foreach ($line in Get-Content -LiteralPath $localAgentEnv) {
        if ($line -match '^\s*(GCA_MODE|GCA_API_KEY|GCA_BASE_URL|GCA_TEXT_MODEL|GCA_VISION_MODEL)\s*=\s*(.*?)\s*$') {
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            $settings[$Matches[1]] = $value
        }
    }
    $hasLiveSetting = $false
    foreach ($name in @('GCA_API_KEY', 'GCA_BASE_URL', 'GCA_TEXT_MODEL', 'GCA_VISION_MODEL')) {
        if ($settings.ContainsKey($name) -and $settings[$name]) { $hasLiveSetting = $true }
    }
    if (($settings.ContainsKey('GCA_MODE') -and $settings['GCA_MODE'] -and $settings['GCA_MODE'] -ine 'mock') -or $hasLiveSetting) {
        throw 'Local Agent live settings are present. This launcher only starts mock mode; temporarily remove them from .env.agent.local and retry.'
    }
}

$agentEnvironmentNames = @('GCA_MODE', 'GCA_API_KEY', 'GCA_BASE_URL', 'GCA_TEXT_MODEL', 'GCA_VISION_MODEL')
$previousAgentEnvironment = @{}
foreach ($name in $agentEnvironmentNames) {
    $previousAgentEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    [Environment]::SetEnvironmentVariable($name, '', 'Process')
}
[Environment]::SetEnvironmentVariable('GCA_MODE', 'mock', 'Process')

function Restore-AgentEnvironment {
    foreach ($name in $agentEnvironmentNames) {
        [Environment]::SetEnvironmentVariable($name, $previousAgentEnvironment[$name], 'Process')
    }
}

function Show-ApiStartupFailureLogs {
    $composeFile = Join-Path $root 'compose.phone-demo.yaml'
    $envFile = Join-Path $root 'phone-demo.env'
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker -or -not (Test-Path -LiteralPath $composeFile -PathType Leaf) -or -not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        Write-Host 'API logs are unavailable because Docker or the local demo files could not be found.'
        return
    }

    $logLines = @(& $docker.Source compose -f $composeFile --env-file $envFile -p $composeProject logs --no-color --tail 80 api 2>&1)
    $logExitCode = $LASTEXITCODE
    if ($logExitCode -ne 0 -or $logLines.Count -eq 0) {
        Write-Host 'No API log output was available for this project.'
        return
    }

    $secretValues = New-Object 'System.Collections.Generic.List[string]'
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^([A-Z0-9_]+)=(.*)$' -and $Matches[1] -match '(PASSWORD|TOKEN|SECRET|KEY|PEPPER|KEK)' -and $Matches[2].Length -ge 4) {
            $secretValues.Add($Matches[2])
        }
    }
    foreach ($line in $logLines) {
        $safeLine = [string]$line
        foreach ($secretValue in $secretValues) { $safeLine = $safeLine.Replace($secretValue, '[REDACTED]') }
        $safeLine = [regex]::Replace($safeLine, '(?i)(password|token|secret|api[_-]?key)(\s*[:=]\s*)[^\s,;]+', '$1$2[REDACTED]')
        Write-Host $safeLine
    }
}

Write-Host 'Starting the isolated GutCare demo in mock mode. First startup may download container images and prepare the pinned MinIO runtime.'
try {
    & (Join-Path $root 'scripts\phone-demo-agent-up.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'The existing phone-demo Agent startup script returned a failure code.'
    }
} catch {
    Restore-AgentEnvironment
    $failureReason = $_.Exception.Message
    Write-Host "API logs for project '$composeProject' (sensitive values redacted):"
    Show-ApiStartupFailureLogs
    throw "GutCare demo startup failed: $failureReason No cleanup was performed; review the API logs above and retry."
}

$healthUri = 'http://127.0.0.1:8000/health/live'
$deadline = (Get-Date).AddSeconds($HealthTimeoutSeconds)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri $healthUri -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 300) {
            $healthy = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}
if (-not $healthy) {
    Restore-AgentEnvironment
    Write-Host "API logs for project '$composeProject' (sensitive values redacted):"
    Show-ApiStartupFailureLogs
    throw "API health check did not succeed within $HealthTimeoutSeconds seconds. Services and demo data were left untouched; review the API logs above."
}

Restore-AgentEnvironment
Write-Host 'GutCare demo is ready at http://127.0.0.1:8000/health/live. Agent mode: mock. Android APK is present at android\app-debug.apk.'
Write-Host 'Use .\Stop-GutCareDemo.ps1 to stop services; demo data will be kept.'
