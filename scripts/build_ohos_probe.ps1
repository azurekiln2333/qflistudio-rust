param(
  [Parameter(Mandatory = $true)]
  [string]$SdkRoot,
  [string]$Rustc = 'rustc',
  [ValidateSet('arm64', 'x64')]
  [string]$Architecture = 'arm64'
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
if ($Architecture -eq 'x64') {
  $rustTarget = 'x86_64-unknown-linux-ohos'
  $clangTarget = 'x86_64-linux-ohos'
  $abi = 'x86_64'
  $machine = 'Advanced Micro Devices X86-64'
} else {
  $rustTarget = 'aarch64-unknown-linux-ohos'
  $clangTarget = 'aarch64-linux-ohos'
  $abi = 'arm64-v8a'
  $machine = 'AArch64'
}
$outputDir = Join-Path $projectRoot "ohos/entry/libs/$abi"
$output = Join-Path $outputDir 'libqfli_native_probe.so'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
if (Test-Path -LiteralPath $output) {
  Remove-Item -LiteralPath $output
}

& $Rustc '--crate-type=cdylib' '--edition=2021' "--target=$rustTarget" `
  '-C' "linker=$clang" '-C' "link-arg=--target=$clangTarget" `
  '-C' "link-arg=--sysroot=$sysroot" '-o' $output $source
if ($LASTEXITCODE -ne 0) { throw "rustc failed with exit code $LASTEXITCODE" }

$header = & $readelf '-h' $output
if ($LASTEXITCODE -ne 0 -or -not ($header -match [regex]::Escape($machine))) {
  throw "The output is not an ELF library for $Architecture."
}
$symbols = & $nm '-D' $output
if ($LASTEXITCODE -ne 0 -or -not ($symbols -match 'qfli_native_probe')) {
  throw 'The native probe symbol is missing.'
}
Write-Output "Built $output"
