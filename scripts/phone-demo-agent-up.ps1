[CmdletBinding()]
param([switch]$NoBuild)

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
    $processValue = [Environment]::GetEnvironmentVariable($Name, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($processValue)) { return $processValue.Trim() }
    if ($agentSettings.ContainsKey($Name)) { return [string]$agentSettings[$Name] }
    return ''
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
$composeArgs += @('-p', 'gutcare-phone-demo', 'up', '-d')
if ($NoBuild) { $composeArgs += '--no-build' } else { $composeArgs += '--build' }
$composeArgs += @('--wait', 'agent', 'analysis-dispatcher')
& $docker.Source @composeArgs
if ($LASTEXITCODE -ne 0) { throw 'F08 Agent profile failed to start; inspect project-scoped logs.' }
if ($mode -eq 'live') {
    Write-Host 'F08 Agent profile is ready in live model mode. The API key is not displayed.'
} else {
    Write-Host "F08 Agent profile is ready in $mode mode."
}
