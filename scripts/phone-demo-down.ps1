[CmdletBinding()]
param(
    [switch]$PurgeData,
    [string[]]$ExpectedContainerIds
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root 'compose.phone-demo.yaml'
$envFile = Join-Path $root 'phone-demo.env'
$project = 'gutcare-competition-demo'
# Keep Go-template quotes in a PowerShell single-quoted value.  Passing the
# value as a variable prevents PowerShell from treating the label key as a
# command expression or stripping the inner double quotes.
$containerProjectLabelTemplate = '{{ index .Config.Labels "com.docker.compose.project" }}'
$volumeProjectLabelTemplate = '{{ index .Labels "com.docker.compose.project" }}'
if (-not (Test-Path -LiteralPath $composeFile -PathType Leaf) -or -not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'The phone-demo files are missing; no Docker resource was changed.'
}
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) { throw 'Environment blocked: Docker CLI is unavailable; no services were changed.' }
Set-Location $root
$containers = @(& $docker.Source ps -aq --no-trunc --filter "label=com.docker.compose.project=$project")
if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Docker project resources; no services were changed.' }
$actualIds = @($containers | Where-Object { $_ } | ForEach-Object { ([string]$_).Trim() } | Sort-Object)
if ($PSBoundParameters.ContainsKey('ExpectedContainerIds')) {
    $expectedIds = @($ExpectedContainerIds | Where-Object { $_ } | ForEach-Object { ([string]$_).Trim() } | Sort-Object)
    if ($expectedIds.Count -eq 0 -or $actualIds.Count -ne $expectedIds.Count -or (($actualIds -join ',') -cne ($expectedIds -join ','))) {
        throw 'Refusing cleanup: current phone-demo container IDs differ from the caller-verified startup IDs.'
    }
}
foreach ($container in $containers) {
    if (-not $container) { continue }
    $label = & $docker.Source inspect --format $containerProjectLabelTemplate $container
    if ($LASTEXITCODE -ne 0 -or $label -ne $project) { throw 'Refusing cleanup: a selected container is outside the phone-demo project.' }
}
$args = @('compose', '-f', $composeFile, '--env-file', $envFile, '-p', $project, 'down', '--remove-orphans')
if ($PurgeData) {
    $volumes = @(& $docker.Source volume ls -q --filter "label=com.docker.compose.project=$project")
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect Docker volumes; no services were changed.' }
    foreach ($volume in $volumes) {
        if (-not $volume) { continue }
        $label = & $docker.Source volume inspect --format $volumeProjectLabelTemplate $volume
        if ($LASTEXITCODE -ne 0 -or $label -ne $project) { throw 'Refusing cleanup: a selected volume is outside the phone-demo project.' }
    }
    $args += '--volumes'
}
& $docker.Source @args
if ($LASTEXITCODE -ne 0) { throw 'Phone-demo shutdown failed.' }
Write-Host ($(if ($PurgeData) { 'Phone-demo containers and all project volumes were removed, including uploaded demo objects.' } else { 'Phone-demo containers were stopped; database, uploaded demo objects and service data volumes were kept.' }))
