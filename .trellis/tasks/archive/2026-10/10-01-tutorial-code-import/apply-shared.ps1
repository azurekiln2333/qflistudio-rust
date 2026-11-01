param([string]$Patch = 'shared.patch')
$ErrorActionPreference = 'Stop'
$content = Get-Content -LiteralPath (Join-Path $PSScriptRoot $Patch) -Raw
$shim = Get-Content -LiteralPath (Get-Command apply_patch).Source -Raw
if ($shim -notmatch '"([^"]+codex\.exe)"') { throw 'Cannot locate the apply_patch executable.' }
& $Matches[1] --codex-run-as-apply-patch $content
if ($LASTEXITCODE -ne 0) { throw 'Shared patch application failed.' }
