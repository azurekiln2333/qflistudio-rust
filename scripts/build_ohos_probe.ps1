param(
  [Parameter(Mandatory = $true)]
  [string]$SdkRoot,
  [string]$Rustc = 'rustc'
)

$ErrorActionPreference = 'Stop'
$clang = Join-Path $SdkRoot 'native/llvm/bin/clang.exe'
$sysroot = Join-Path $SdkRoot 'native/sysroot'
$readelf = Join-Path $SdkRoot 'native/llvm/bin/llvm-readelf.exe'
$nm = Join-Path $SdkRoot 'native/llvm/bin/llvm-nm.exe'
foreach ($required in @($clang, $sysroot, $readelf, $nm)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Missing OHOS SDK input: $required"
  }
}

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = Join-Path $projectRoot 'native/ohos_probe.rs'
$outputDir = Join-Path $projectRoot 'ohos/entry/libs/arm64-v8a'
$output = Join-Path $outputDir 'libqfli_native_probe.so'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
if (Test-Path -LiteralPath $output) {
  Remove-Item -LiteralPath $output
}

& $Rustc '--crate-type=cdylib' '--edition=2021' '--target=aarch64-unknown-linux-ohos' `
  '-C' "linker=$clang" '-C' 'link-arg=--target=aarch64-linux-ohos' `
  '-C' "link-arg=--sysroot=$sysroot" '-o' $output $source
if ($LASTEXITCODE -ne 0) { throw "rustc failed with exit code $LASTEXITCODE" }

$header = & $readelf '-h' $output
if ($LASTEXITCODE -ne 0 -or -not ($header -match 'AArch64')) {
  throw 'The output is not an AArch64 ELF library.'
}
$symbols = & $nm '-D' $output
if ($LASTEXITCODE -ne 0 -or -not ($symbols -match 'qfli_native_probe')) {
  throw 'The native probe symbol is missing.'
}
Write-Output "Built $output"
