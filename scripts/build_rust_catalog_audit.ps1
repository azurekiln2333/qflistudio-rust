param(
    [ValidateSet('ohos-x64', 'ohos-arm64')][string]$Architecture = 'ohos-x64',
    [Parameter(Mandatory = $true)][string]$CompilerRecord,
    [Parameter(Mandatory = $true)][string]$AdapterRecord,
    [string]$Json5Module = 'D:/ProgramFiles/Huawei/DevEco Studio/tools/hvigor/hvigor-ohos-plugin/node_modules/json5'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
# The audit archive is only trustworthy when the packaged adapter is bound to
# the patched compiler that produced it. Both trusted build records are
# resolved and hashed before any staging, build or output mutation, so a
# missing or unusable record cannot leave a half-prepared audit tree behind.
function Resolve-TrustedRecord([string]$Label, [string]$Path) {
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    if (-not [IO.File]::Exists($resolved)) { throw "$Label is not a file: $resolved" }
    if ([IO.FileInfo]::new($resolved).Length -eq 0) { throw "$Label is empty: $resolved" }
    return $resolved
}
$compilerRecordPath = Resolve-TrustedRecord 'Compiler build record' $CompilerRecord
$adapterRecordPath = Resolve-TrustedRecord 'Adapter build record' $AdapterRecord
$compilerRecordSha256 = (Get-FileHash -LiteralPath $compilerRecordPath -Algorithm SHA256).Hash.ToLowerInvariant()
$adapterRecordSha256 = (Get-FileHash -LiteralPath $adapterRecordPath -Algorithm SHA256).Hash.ToLowerInvariant()
$output = Join-Path $repo "build/offline-ide-audit/$Architecture"
[IO.Directory]::CreateDirectory($output) | Out-Null
$lockPath = Join-Path $repo 'build/offline-ide-audit/.hap-build-lock'
$lock = [IO.File]::Open($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
$paths = @(
    (Join-Path $repo 'ohos/AppScope/app.json5'),
    (Join-Path $repo 'ohos/entry/build-profile.json5'),
    (Join-Path $repo 'ohos/hvigor/hvigor-config.json5')
)
$original = @{}
$temporaryHashes = @{}
$mutated = $false
$locationPushed = $false
$bundle = 'com.azurekiln.qfli.rust.audit'
$target = 'lib/main_catalog_audit.dart'
$buildId = [Guid]::NewGuid().ToString('N')
try {
    foreach ($path in $paths) { $original[$path] = [IO.File]::ReadAllBytes($path) }
    Push-Location $repo
    $locationPushed = $true
    & python scripts/generate_rust_content.py --check *> (Join-Path $output 'content-check.log')
    if ($LASTEXITCODE -ne 0) { throw 'Rust content generation check failed.' }
    & python scripts/generate_rust_native_catalog.py --check *> (Join-Path $output 'catalog-check.log')
    if ($LASTEXITCODE -ne 0) { throw 'Native catalog generation check failed.' }
    & python scripts/check_native_packaging.py --ohos-assets assets/miri --ohos-libraries ohos/entry/libs `
        *> (Join-Path $output 'native-check.log')
    if ($LASTEXITCODE -ne 0) { throw 'Native runtime asset/ELF/dependency check failed.' }
    # Use the parser bundled with Hvigor. Signing inputs in the root profile
    # remain untouched; the typed Hvigor property disables the signing task.
    $edit = @'
const fs = require('fs'), json5 = require(process.argv[1]);
const paths = process.argv.slice(2, 5), architecture = process.argv[5];
const values = paths.map(path => json5.parse(fs.readFileSync(path, 'utf8')));
if (values[0].app.bundleName !== 'com.azurekiln.qfli.rust') {
  throw new Error('Expected the Rust production bundle before isolation');
}
values[0].app.bundleName = 'com.azurekiln.qfli.rust.audit';
const native = values[1].buildOption.nativeLib;
native.filter = {...native.filter, excludes: [architecture === 'ohos-x64' ? '**/arm64-v8a/**' : '**/x86_64/**']};
values[2].properties = {...values[2].properties, enableSignTask: false};
paths.forEach((path, index) => fs.writeFileSync(path, JSON.stringify(values[index], null, 2) + '\n'));
'@
    $mutated = $true
    & node -e $edit $Json5Module $paths[0] $paths[1] $paths[2] $Architecture
    if ($LASTEXITCODE -ne 0) { throw 'Unable to prepare isolated audit metadata.' }
    foreach ($path in $paths) {
        $temporaryHashes[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    }
    $arguments = @('build', 'hap', '--release', '--target-platform', $Architecture,
        '--no-codesign', '--target', $target, "--dart-define=QFLI_RUST_AUDIT_BUILD_ID=$buildId")
    & flutter @arguments *> (Join-Path $output 'build.log')
    if ($LASTEXITCODE -ne 0) { throw "Audit HAP build failed; inspect $output/build.log." }
    $unsigned = Join-Path $repo 'ohos/entry/build/default/outputs/default/entry-default-unsigned.hap'
    $digest = (Get-FileHash -LiteralPath $unsigned -Algorithm SHA256).Hash.ToLowerInvariant()
    $artifact = Join-Path $output "rust-catalog-$digest-unsigned.hap"
    if (Test-Path -LiteralPath $artifact) {
        if ((Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) {
            throw 'Existing hash-named artifact has different bytes.'
        }
    } else { Copy-Item -LiteralPath $unsigned -Destination $artifact }
    $metadata = Join-Path $output 'build.json'
    @{
        bundleName = $bundle; architecture = $Architecture; target = $target
        buildId = $buildId; builtAt = [DateTime]::UtcNow.ToString('o')
        artifact = $artifact; sha256 = $digest; signed = $false; deviceExecuted = $false
        compilerRecordSha256 = $compilerRecordSha256; adapterRecordSha256 = $adapterRecordSha256
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $metadata -Encoding utf8
    & python scripts/inspect_rust_catalog_hap.py --hap $artifact --architecture $Architecture `
        --compiler-record $compilerRecordPath --adapter-record $adapterRecordPath `
        --metadata $metadata --report (Join-Path $output 'inspection.json')
    if ($LASTEXITCODE -ne 0) { throw 'Final audit HAP archive verification failed.' }
    Write-Output "Verified unsigned audit HAP: $artifact"
} finally {
    $restoreIssues = @()
    try {
        if ($mutated) {
            for ($index = 0; $index -lt $paths.Count; $index++) {
                $path = $paths[$index]
                if ($temporaryHashes.ContainsKey($path) -and
                    (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $temporaryHashes[$path]) {
                    [IO.File]::WriteAllBytes((Join-Path $output "original-$index.backup"), $original[$path])
                    $restoreIssues += "Concurrent edit preserved at $path; original bytes in original-$index.backup"
                } else { [IO.File]::WriteAllBytes($path, $original[$path]) }
            }
        }
    } finally {
        if ($locationPushed) { Pop-Location }
        $lock.Dispose()
        Remove-Item -LiteralPath $lockPath
    }
    if ($restoreIssues.Count -gt 0) { throw ($restoreIssues -join "`n") }
}
