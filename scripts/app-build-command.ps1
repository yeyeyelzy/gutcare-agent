function Invoke-AppBuildCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string] $FilePath,
        [Parameter(Mandatory = $true)][object[]] $ArgumentList,
        [Parameter(Mandatory = $true)][string] $TargetName
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 promotes native stderr records to error records.
        # Keep stderr attached to the console, but do not mistake warning output
        # for command failure; the process exit code remains authoritative.
        $ErrorActionPreference = 'Continue'
        & $FilePath @ArgumentList
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "APP $TargetName build failed (exit=$exitCode)."
    }
}
