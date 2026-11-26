param(
    [Parameter(Mandatory)][string]$TextFile,
    [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9_-]*$')][string]$NextOwner
)
$ErrorActionPreference = 'Stop'
$recipients = "$NextOwner,c-coordinator,go-offline-1022,web-offline-1022,json-offline-1022,note-offline-1022,java-offline-1022"
& trellis channel send qfli-core-release-sync --scope global --as rust-offline-1022 `
    --to $recipients --text-file $TextFile
exit $LASTEXITCODE
