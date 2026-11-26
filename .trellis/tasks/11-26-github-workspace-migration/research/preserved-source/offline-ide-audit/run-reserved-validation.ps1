param(
    [Parameter(Mandatory)][ValidateSet('Native', 'Dart')][string]$Mode,
    [Parameter(Mandatory)][ValidateRange(534, 2147483647)][int]$GrantSeq,
    [Parameter(Mandatory)][string]$GrantEvidenceFile,
    [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9_-]*$')][string]$NextOwner,
    [Parameter(Mandatory)][switch]$RootVerifiedGrant
)
$ErrorActionPreference = 'Stop'
if (-not $RootVerifiedGrant.IsPresent) {
    throw 'Root must verify the current named handoff immediately before launch.'
}
$pythonExecutable = (Get-Command python -CommandType Application -ErrorAction Stop |
    Select-Object -First 1).Source
$runner = Join-Path $PSScriptRoot 'run-rust-owned-window.py'
$grantFile = (Resolve-Path -LiteralPath $GrantEvidenceFile -ErrorAction Stop).Path
& $pythonExecutable $runner --mode $Mode --grant-seq $GrantSeq `
    --grant-evidence-file $grantFile --next-owner $NextOwner --root-verified-grant
exit $LASTEXITCODE
