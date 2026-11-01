$ErrorActionPreference = 'Stop'
$files = @{
    'local_content_pages.dart' = 'lib/pages/local_content_pages.dart'
    'content_code_import_test.dart' = 'test/content_code_import_test.dart'
}
$sharedRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../../qfli_studio_core'))
$lines = [Collections.Generic.List[string]]::new()
$lines.Add('*** Begin Patch')
foreach ($entry in $files.GetEnumerator()) {
    $before = Join-Path $PSScriptRoot "review/snapshots/$($entry.Key)"
    $after = Join-Path $PSScriptRoot "review/work/$($entry.Key)"
    $destination = Join-Path $sharedRoot $entry.Value
    $difference = @(& git -c core.autocrlf=false diff --no-index --no-ext-diff -- $before $after)
    if ($LASTEXITCODE -gt 1) { throw "Cannot diff $($entry.Key)." }
    if ($difference.Count -eq 0) { continue }
    $lines.Add("*** Update File: $($destination.Replace('\', '/'))")
    $inHunk = $false
    foreach ($line in $difference) {
        if ($line.StartsWith('@@ ')) {
            $lines.Add('@@')
            $inHunk = $true
        } elseif ($inHunk -and !$line.StartsWith('\ No newline')) {
            $lines.Add($line)
        }
    }
}
$lines.Add('*** End Patch')
[IO.File]::WriteAllText(
    (Join-Path $PSScriptRoot 'review.patch'),
    ($lines -join "`n") + "`n",
    [Text.UTF8Encoding]::new($false)
)
Write-Output "Prepared $($lines.Count) patch lines."
