param(
  [Parameter(Mandatory = $true)][string]$MiriSource,
  [Parameter(Mandatory = $true)][string]$Toolchain,
  [Parameter(Mandatory = $true)][string]$CompilerSysroot,
  [Parameter(Mandatory = $true)][string]$RuntimeSysroot,
  [Parameter(Mandatory = $true)][string]$CompilerBuildInfo,
  [string]$BuildRoot = (Join-Path $PSScriptRoot '../native/build/miri-windows'),
  [string]$CargoHome = $env:CARGO_HOME,
  [string]$PatchExecutable = 'patch',
  [string]$PythonExecutable = 'python',
  [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$MiriSource = (Resolve-Path -LiteralPath $MiriSource).Path
$Toolchain = (Resolve-Path -LiteralPath $Toolchain).Path
$CompilerSysroot = (Resolve-Path -LiteralPath $CompilerSysroot).Path
$RuntimeSysroot = (Resolve-Path -LiteralPath $RuntimeSysroot).Path
$CompilerBuildInfo = (Resolve-Path -LiteralPath $CompilerBuildInfo).Path
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$hostTriple = 'x86_64-pc-windows-gnu'
$rustc = Join-Path $Toolchain 'bin/rustc.exe'
$cargo = Join-Path $Toolchain 'bin/cargo.exe'
$version = (& $rustc -vV) -join "`n"
if ($LASTEXITCODE -ne 0 -or $version -notmatch '(?m)^commit-hash: 48a229ceaefd4985c50990b14116b6d856af0985$' -or
    $version -notmatch "(?m)^host: $hostTriple`$") {
  throw 'Use the pinned Windows GNU Rust 1.98.1 build compiler.'
}
# Resolve comparisons in Python's Windows path semantics, including aliases.
$buildSupport = Join-Path $PSScriptRoot 'miri_build_support.py'
& $PythonExecutable $buildSupport 'check-build-root' '--build-root' $BuildRoot `
  '--input-root' $MiriSource '--input-root' $Toolchain `
  '--input-root' $CompilerSysroot '--input-root' $RuntimeSysroot `
  '--input-root' $CompilerBuildInfo '--input-root' (Join-Path $projectRoot 'native/miri_adapter')
if ($LASTEXITCODE -ne 0) { throw 'Build output overlaps a protected compiler input.' }
if ($CargoHome) {
  & $PythonExecutable $buildSupport 'check-build-root' '--build-root' $CargoHome `
    '--input-root' $MiriSource '--input-root' $Toolchain `
    '--input-root' $CompilerSysroot '--input-root' $RuntimeSysroot `
    '--input-root' $CompilerBuildInfo '--input-root' (Join-Path $projectRoot 'native/miri_adapter')
  if ($LASTEXITCODE -ne 0) { throw 'Cargo cache overlaps a protected compiler input.' }
}
$helper = Join-Path $PSScriptRoot 'prepare_miri_windows.py'
& $PythonExecutable $helper 'verify-source' $MiriSource
if ($LASTEXITCODE -ne 0) { throw 'Pinned Miri source verification failed.' }

$compiler = $CompilerSysroot
$miriStage = Join-Path $BuildRoot 'miri'
$adapterStage = Join-Path $BuildRoot 'adapter'
# There is no official rustc-dev fallback: the adapter uses patched private types.
& $PythonExecutable $buildSupport 'check-compiler' '--compiler-build-info' $CompilerBuildInfo `
  '--compiler-sysroot' $CompilerSysroot '--runtime-sysroot' $RuntimeSysroot '--native-host' $hostTriple
if ($LASTEXITCODE -ne 0) { throw 'A verified rebuilt Windows compiler sysroot is required.' }
New-Item -ItemType Directory -Force -Path $BuildRoot, $miriStage, $adapterStage | Out-Null
Copy-Item -Path (Join-Path $MiriSource '*') -Destination $miriStage -Recurse -Force
Copy-Item -Path (Join-Path $projectRoot 'native/miri_adapter/*') -Destination $adapterStage -Recurse -Force
& $PythonExecutable $helper 'normalize-stage' $miriStage
if ($LASTEXITCODE -ne 0) { throw 'Staged Miri source verification failed.' }
& $PatchExecutable '--fuzz=0' '--no-backup-if-mismatch' '-d' $miriStage '-p1' '-i' `
  (Join-Path $projectRoot 'native/patches/miri-1.98.1-embedded-session.patch')
if ($LASTEXITCODE -ne 0) { throw 'Embedded Miri patch failed.' }

$linker = Join-Path $Toolchain "lib/rustlib/$hostTriple/bin/rust-lld.exe"
if (-not (Test-Path -LiteralPath $linker)) { throw 'The bundled Rust LLD linker is missing.' }
$environmentNames = @('PATH', 'CARGO_HOME', 'CARGO_TARGET_DIR', 'RUSTC', 'RUSTC_WRAPPER',
  'RUSTC_WORKSPACE_WRAPPER', 'RUSTC_BOOTSTRAP', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS')
$previous = @{}
foreach ($name in $environmentNames) { $previous[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
  $env:PATH = "$(Join-Path $RuntimeSysroot 'bin');$(Join-Path $Toolchain 'bin');$env:PATH"
  if ($CargoHome) { $env:CARGO_HOME = $CargoHome }
  $env:CARGO_TARGET_DIR = Join-Path $BuildRoot 'target'
  $env:RUSTC = $rustc
  $env:RUSTC_BOOTSTRAP = '1'
  Remove-Item Env:RUSTC_WRAPPER, Env:RUSTC_WORKSPACE_WRAPPER, Env:RUSTFLAGS -ErrorAction SilentlyContinue
  $env:CARGO_ENCODED_RUSTFLAGS = (@("--sysroot=$compiler", '-Cprefer-dynamic',
    "-Lnative=$(Join-Path $RuntimeSysroot 'bin')", "-Lnative=$(Join-Path $RuntimeSysroot 'lib')",
    "-Lnative=$(Join-Path $compiler "lib/rustlib/$hostTriple/lib")", '-Clinker-flavor=ld.lld' , "-Clinker=$linker",
    '-Clink-self-contained=yes') -join [char]31)
  $arguments = @('rustc', '--manifest-path', (Join-Path $adapterStage 'Cargo.toml'),
    '--target', $hostTriple, '--locked', '--lib')
  if ($Offline) { $arguments += '--offline' }
  & $cargo @arguments
  if ($LASTEXITCODE -ne 0) { throw 'Windows Miri adapter compilation failed.' }
  $metadataArguments = @('metadata', '--manifest-path', (Join-Path $adapterStage 'Cargo.toml'),
    '--locked', '--format-version=1', '--filter-platform', $hostTriple)
  if ($Offline) { $metadataArguments += '--offline' }
  $metadata = & $cargo @metadataArguments
  if ($LASTEXITCODE -ne 0) { throw 'Native dependency metadata generation failed.' }
  [IO.File]::WriteAllText((Join-Path $BuildRoot "dependencies-$hostTriple.json"), ($metadata -join "`n"),
    [Text.UTF8Encoding]::new($false))
} finally {
  foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previous[$name]) }
}
& $PythonExecutable $buildSupport '--toolchain' $Toolchain `
  '--compiler-build-info' $CompilerBuildInfo '--compiler-sysroot' $CompilerSysroot `
  '--runtime-sysroot' $RuntimeSysroot '--miri-source' $MiriSource '--native-host' $hostTriple `
  '--adapter' (Join-Path $BuildRoot "target/$hostTriple/debug/qfli_miri.dll") `
  '--dependency-metadata' (Join-Path $BuildRoot "dependencies-$hostTriple.json") `
  '--output' (Join-Path $BuildRoot "adapter-build-$hostTriple.json")
if ($LASTEXITCODE -ne 0) { throw 'Patched compiler provenance recording failed.' }
Write-Output "Adapter: $(Join-Path $BuildRoot "target/$hostTriple/debug/qfli_miri.dll")"
Write-Output "Compiler runtime: $RuntimeSysroot"
