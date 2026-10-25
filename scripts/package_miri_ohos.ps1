param(
  [Parameter(Mandatory = $true)][string]$AdapterLibrary,
  [Parameter(Mandatory = $true)][string]$AdapterBuildInfo,
  [Parameter(Mandatory = $true)][string]$CompilerLibDirectory,
  [Parameter(Mandatory = $true)][string]$GuestSysroot,
  [Parameter(Mandatory = $true)][string]$SdkRoot,
  [Parameter(Mandatory = $true)][string]$RustSource,
  [Parameter(Mandatory = $true)][string]$DependencyMetadata,
  [string]$CodegenBackend,
  [ValidateSet('arm64', 'x64')][string]$Architecture = 'arm64',
  [string]$WslDistro = 'qfli-java-build',
  [string]$PythonExecutable = 'python'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$readobj = Join-Path $SdkRoot 'native/llvm/bin/llvm-readobj.exe'
$readelf = Join-Path $SdkRoot 'native/llvm/bin/llvm-readelf.exe'
if ($Architecture -eq 'x64') {
  $abi = 'x86_64'
  $elfArch = 'x86_64'
  $hostTarget = 'x86_64-unknown-linux-ohos'
  $clangTarget = 'x86_64-linux-ohos'
  if (-not $CodegenBackend) { throw 'The x64 build requires its matching Cranelift backend.' }
} else {
  $abi = 'arm64-v8a'
  $elfArch = 'aarch64'
  $hostTarget = 'aarch64-unknown-linux-ohos'
  $clangTarget = 'aarch64-linux-ohos'
}
$guestTarget = 'x86_64-unknown-linux-gnu'
$guestLibraries = Join-Path $GuestSysroot "lib/rustlib/$guestTarget/lib"
foreach ($required in @($readobj, $readelf, $AdapterLibrary, $AdapterBuildInfo, $CompilerLibDirectory,
    $guestLibraries, $RustSource, $DependencyMetadata)) {
  if (-not (Test-Path -LiteralPath $required)) { throw "Missing package input: $required" }
}

function Assert-Architecture([string]$Path) {
  $json = & $readobj '--elf-output-style=JSON' '--file-headers' $Path
  if ($LASTEXITCODE -ne 0) { throw "Cannot inspect ELF: $Path" }
  $document = ($json -join "`n") | ConvertFrom-Json
  $info = @($document)[0].PSObject.Properties.Value
  if ($info.FileSummary.Arch -ne $elfArch -or $info.ElfHeader.Type -ne 'SharedObject (0x3)') {
    throw "Expected a $elfArch shared library: $Path"
  }
}

function Get-NeededLibraries([string]$Path) {
  $lines = & $readelf '-d' $Path
  if ($LASTEXITCODE -ne 0) { throw "Cannot inspect dependencies: $Path" }
  # SDK LLVM 15 emits invalid JSON for needed-libs, so read its tagged ELF rows.
  foreach ($line in $lines) {
    if ($line -match '\(NEEDED\).*\[([^\]]+)\]') { $Matches[1] }
  }
}

function Resolve-LinuxInput([string]$Path) {
  if ($Path -match '^/mnt/([a-z])/(.*)$') {
    return "$(($Matches[1]).ToUpper()):\$($Matches[2].Replace('/', '\'))"
  }
  if ($Path.StartsWith('/')) { return "\\wsl.localhost\$WslDistro$($Path.Replace('/', '\'))" }
  return $Path
}

# Validate producer paths through the explicitly selected WSL distribution.
# This reads records and hashes only; the helper does not launch WSL.
$buildSupport = Join-Path $PSScriptRoot 'miri_build_support.py'
$verifiedJson = & $PythonExecutable $buildSupport 'verify-adapter' `
  '--adapter-build-info' $AdapterBuildInfo '--adapter' $AdapterLibrary `
  '--native-host' $hostTarget '--wsl-distro' $WslDistro
if ($LASTEXITCODE -ne 0) { throw 'Patched compiler and adapter provenance verification failed.' }
$adapterRecord = ($verifiedJson -join "`n") | ConvertFrom-Json
$metadataHash = (Get-FileHash -LiteralPath $DependencyMetadata -Algorithm SHA256).Hash.ToLowerInvariant()
if ($metadataHash -ne $adapterRecord.dependencyMetadata.sha256) {
  throw 'Dependency metadata differs from the verified adapter build record.'
}
$compilerRecords = @($adapterRecord.compilerLibraries)
if ($CodegenBackend) {
  $backendName = [IO.Path]::GetFileName($CodegenBackend)
  $backendHash = (Get-FileHash -LiteralPath $CodegenBackend -Algorithm SHA256).Hash.ToLowerInvariant()
  if (-not @($compilerRecords | Where-Object { $_.name -eq $backendName -and $_.sha256 -eq $backendHash }).Count) {
    throw 'Selected codegen backend differs from the verified compiler build.'
  }
}

$searchDirs = @(
  (Split-Path -Parent $AdapterLibrary), $CompilerLibDirectory,
  (Join-Path $SdkRoot "native/llvm/lib/$clangTarget"),
  (Join-Path $SdkRoot "native/sysroot/usr/lib/$clangTarget")
)
if ($CodegenBackend) { $searchDirs += Split-Path -Parent $CodegenBackend }
$nativeFiles = [ordered]@{}
$nativeHashes = [ordered]@{}
$queue = [System.Collections.Generic.Queue[string]]::new()
$queue.Enqueue($AdapterLibrary)
if ($CodegenBackend) { $queue.Enqueue($CodegenBackend) }
while ($queue.Count -gt 0) {
  $file = $queue.Dequeue()
  $name = [System.IO.Path]::GetFileName($file)
  if ($nativeFiles.Contains($name)) { continue }
  Assert-Architecture $file
  $nativeFiles[$name] = $file
  $nativeHashes[$name] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($name -eq 'libqfli_miri.so') {
    if ($nativeHashes[$name] -ne $adapterRecord.adapter.sha256) {
      throw 'Adapter changed after provenance verification.'
    }
  } elseif ($name -match 'rustc_driver|rustc_codegen|^libstd-|^libLLVM') {
    if (-not @($compilerRecords | Where-Object { $_.name -eq $name -and $_.sha256 -eq $nativeHashes[$name] }).Count) {
      throw "Compiler dependency differs from verified build: $name"
    }
  }
  foreach ($needed in (Get-NeededLibraries $file)) {
    if ($needed -in @('libc.so', 'libdl.so', 'libm.so', 'libpthread.so', 'librt.so')) { continue }
    $dependency = $null
    foreach ($directory in $searchDirs) {
      $candidate = Join-Path $directory $needed
      if (Test-Path -LiteralPath $candidate -PathType Leaf) { $dependency = $candidate; break }
    }
    if (-not $dependency) { throw "Missing native dependency $needed required by $name" }
    $queue.Enqueue($dependency)
  }
}

$assetRoot = Join-Path $projectRoot 'assets/miri'
$nativeRoot = Join-Path $projectRoot "ohos/entry/libs/$abi"
New-Item -ItemType Directory -Force -Path $assetRoot, $nativeRoot | Out-Null
$assetFiles = [System.Collections.Generic.List[object]]::new()
function Add-Asset([string]$Source, [string]$RelativePath) {
  $digest = (Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant()
  # Flutter directory asset entries include immediate files only.
  $assetName = "$digest.bin"
  $destination = Join-Path $assetRoot $assetName
  Copy-Item -LiteralPath $Source -Destination $destination -Force
  $assetFiles.Add([ordered]@{
    path = $RelativePath.Replace('\', '/')
    asset = $assetName
    size = (Get-Item -LiteralPath $destination).Length
    sha256 = $digest
  })
}

foreach ($name in $nativeFiles.Keys) {
  Copy-Item -LiteralPath $nativeFiles[$name] -Destination (Join-Path $nativeRoot $name) -Force
  $copiedHash = (Get-FileHash -LiteralPath (Join-Path $nativeRoot $name) -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($copiedHash -ne $nativeHashes[$name]) { throw "Native input changed during packaging: $name" }
}
foreach ($file in (Get-ChildItem -LiteralPath $guestLibraries -Filter '*.rlib' -File)) {
  Add-Asset $file.FullName "sysroot/lib/rustlib/$guestTarget/lib/$($file.Name)"
}
if ($CodegenBackend) {
  $backendName = [System.IO.Path]::GetFileName($CodegenBackend)
  Add-Asset $CodegenBackend "sysroot/lib/rustlib/$hostTarget/codegen-backends/$backendName"
}
foreach ($name in @('COPYRIGHT', 'LICENSE-APACHE', 'LICENSE-MIT', 'license-metadata.json')) {
  Add-Asset (Join-Path $RustSource $name) "licenses/rust/$name"
}
foreach ($name in @('LICENSE-APACHE', 'LICENSE-MIT')) {
  Add-Asset (Join-Path $RustSource "src/tools/miri/$name") "licenses/miri/$name"
}

$metadata = Get-Content -LiteralPath $DependencyMetadata -Raw | ConvertFrom-Json
$resolvedIds = @($metadata.resolve.nodes | ForEach-Object { $_.id })
$notices = [System.Collections.Generic.List[object]]::new()
foreach ($package in $metadata.packages) {
  if ($package.id -notin $resolvedIds) { continue }
  $directory = Split-Path -Parent (Resolve-LinuxInput $package.manifest_path)
  $licenseFiles = @(Get-ChildItem -LiteralPath $directory -File | Where-Object {
    $_.Name -match '^(LICENSE|LICENCE|COPYING|NOTICE)([._-].*)?$'
  })
  if ($package.license_file) {
    $explicit = Join-Path $directory $package.license_file
    if (Test-Path -LiteralPath $explicit) { $licenseFiles += Get-Item -LiteralPath $explicit }
  }
  foreach ($file in ($licenseFiles | Sort-Object FullName -Unique)) {
    Add-Asset $file.FullName "licenses/dependencies/$($package.name)-$($package.version)/$($file.Name)"
  }
  $notices.Add([ordered]@{ name = $package.name; version = $package.version; license = $package.license })
}

$manifest = [ordered]@{
  schemaVersion = 1
  compilerBoundary = $adapterRecord.compilerBoundary
  compilerBuildSha256 = $adapterRecord.compilerBuild.sha256
  adapterBuildSha256 = (Get-FileHash -LiteralPath $AdapterBuildInfo -Algorithm SHA256).Hash.ToLowerInvariant()
  rustVersion = '1.98.1'
  rustCommit = '48a229ceaefd4985c50990b14116b6d856af0985'
  nativeHost = $hostTarget
  guestTarget = $guestTarget
  files = @($assetFiles.ToArray())
  nativeLibraries = @($nativeFiles.Keys | ForEach-Object {
    [ordered]@{ name = $_; sha256 = $nativeHashes[$_] }
  })
  dependencies = @($notices.ToArray())
}
$encoded = $manifest | ConvertTo-Json -Depth 16
$hasher = [System.Security.Cryptography.SHA256]::Create()
try {
  $manifest['id'] = [Convert]::ToHexString($hasher.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($encoded))).ToLowerInvariant()
} finally { $hasher.Dispose() }
$manifestPath = Join-Path $assetRoot "manifest.ohos-$Architecture.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 16
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, [System.Text.UTF8Encoding]::new($false))
# The legacy loader supported one OHOS architecture per package. Keep its
# established ARM64 manifest while allowing both new manifests to coexist;
# packaging x64 must never silently replace ARM64's legacy runtime identity.
if ($Architecture -eq 'arm64') {
  $legacyManifestPath = Join-Path $assetRoot 'manifest.json'
  [System.IO.File]::WriteAllText($legacyManifestPath, $manifestJson, [System.Text.UTF8Encoding]::new($false))
  Write-Output "Legacy ARM64 manifest: $legacyManifestPath"
}
Write-Output "Packaged $hostTarget native libraries and $($assetFiles.Count) MIR/license assets."
Write-Output "Manifest: $manifestPath"
