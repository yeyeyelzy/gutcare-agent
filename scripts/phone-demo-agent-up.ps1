[CmdletBinding()]
param(
    [switch]$NoBuild,
    # Use after Python source or runtime environment changes.  The agent source
    # is mounted for development, but a running Python process must be
    # recreated before it imports the new modules.
    [switch]$ForceRecreate
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$localAgentEnv = Join-Path $root '.env.agent.local'
$agentSettings = @{}
if (Test-Path -LiteralPath $localAgentEnv) {
    foreach ($line in Get-Content -LiteralPath $localAgentEnv) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $value = $Matches[2].Trim()
            if ($value.Length -ge 2 -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                 ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            $agentSettings[$Matches[1]] = $value
        }
    }
}

function Get-AgentSetting([string]$Name) {
    if ($agentSettings.ContainsKey($Name)) { return [string]$agentSettings[$Name] }
    $processValue = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($processValue)) { return $processValue.Trim() }
    return ''
}

# Docker Compose lets inherited process variables override --env-file values.
# Mirror the project-local Agent settings into this invocation so an old
# GCA_MODE=mock in the terminal cannot silently replace the requested live
# profile. Values are never written to output or persisted by this script.
foreach ($name in @('GCA_MODE', 'GCA_API_KEY', 'GCA_BASE_URL', 'GCA_TEXT_MODEL', 'GCA_VISION_MODEL', 'GCA_TIMEOUT_S', 'GCA_MAX_RETRIES')) {
    if ($agentSettings.ContainsKey($name) -and -not [string]::IsNullOrWhiteSpace($agentSettings[$name])) {
        [Environment]::SetEnvironmentVariable($name, [string]$agentSettings[$name], 'Process')
    }
}

$mode = Get-AgentSetting 'GCA_MODE'
if ([string]::IsNullOrWhiteSpace($mode)) { $mode = 'mock' }
$mode = $mode.ToLowerInvariant()
if ($mode -eq 'live') {
    $missing = @()
    foreach ($name in @('GCA_API_KEY', 'GCA_BASE_URL', 'GCA_TEXT_MODEL', 'GCA_VISION_MODEL')) {
        if ([string]::IsNullOrWhiteSpace((Get-AgentSetting $name))) { $missing += $name }
    }
    if ($missing.Count -gt 0) {
        throw ("Live mode is missing required local settings: {0}. Fill .env.agent.local or set process environment variables; values are never shown." -f ($missing -join ', '))
    }
}

& (Join-Path $PSScriptRoot 'phone-demo-up.ps1') -NoBuild:$NoBuild
if ($LASTEXITCODE -ne 0) { throw 'Base phone-demo services did not start.' }
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Docker CLI is unavailable.' }
Set-Location $root
$composeArgs = @('compose', '--profile', 'agent', '-f', $composeFile, '--env-file', $envFile)
if (Test-Path -LiteralPath $localAgentEnv) { $composeArgs += @('--env-file', $localAgentEnv) }
$composeArgs += @('-p', 'gutcare-competition-demo', 'up', '-d')
if ($NoBuild) { $composeArgs += '--no-build' } else { $composeArgs += '--build' }
if ($ForceRecreate) { $composeArgs += '--force-recreate' }
$composeArgs += @('--wait', 'agent', 'analysis-dispatcher', 'record-image-dispatcher', 'medical-parse-dispatcher')
& $docker.Source @composeArgs
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo Agent profile failed to start; inspect project-scoped logs.' }

# Verify the process actually received the requested mode.  Container health
# alone is not enough: it can be healthy while accidentally running mock.
$inspectArgs = @('compose', '--profile', 'agent', '-f', $composeFile, '--env-file', $envFile)
if (Test-Path -LiteralPath $localAgentEnv) { $inspectArgs += @('--env-file', $localAgentEnv) }
$inspectArgs += @('-p', 'gutcare-competition-demo', 'exec', '-T', 'agent', 'python', '-c',
    'from gutcare_agents.config import load_settings; print(load_settings().mode)')
$runtimeMode = ((& $docker.Source @inspectArgs | Select-Object -Last 1) -as [string]).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($runtimeMode)) {
    throw 'Agent started but its runtime mode could not be verified.'
}
if ($runtimeMode -eq 'live') {
    Write-Host 'Agent profile is ready in live model mode. The API key is not displayed.'
} else {
    Write-Host 'Agent profile is ready in mock mode.'
}
