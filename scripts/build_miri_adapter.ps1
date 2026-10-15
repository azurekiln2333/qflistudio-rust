param(
  [Parameter(Mandatory = $true)][string]$MiriSource,
  [Parameter(Mandatory = $true)][string]$Toolchain,
  [Parameter(Mandatory = $true)][string]$RustcDevArchive,
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
$RustcDevArchive = (Resolve-Path -LiteralPath $RustcDevArchive).Path
$BuildRoot = [System.IO.Path]::GetFullPath($BuildRoot)
$hostTriple = 'x86_64-pc-windows-gnu'
$rustc = Join-Path $Toolchain 'bin/rustc.exe'
$cargo = Join-Path $Toolchain 'bin/cargo.exe'
$version = (& $rustc -vV) -join "`n"
if ($LASTEXITCODE -ne 0 -or $version -notmatch '(?m)^commit-hash: 48a229ceaefd4985c50990b14116b6d856af0985$' -or
    $version -notmatch "(?m)^host: $hostTriple`$") {
  throw 'Use the pinned official Windows GNU Rust 1.98.1 compiler.'
}
if ($BuildRoot.StartsWith($MiriSource + [IO.Path]::DirectorySeparatorChar) -or $BuildRoot -eq $MiriSource -or
    $BuildRoot.StartsWith($Toolchain + [IO.Path]::DirectorySeparatorChar) -or $BuildRoot -eq $Toolchain) {
  throw 'BuildRoot must be separate from the input source and compiler.'
}
$helper = Join-Path $PSScriptRoot 'prepare_miri_windows.py'
& $PythonExecutable $helper 'verify-source' $MiriSource
if ($LASTEXITCODE -ne 0) { throw 'Pinned Miri source verification failed.' }

$compiler = Join-Path $BuildRoot 'compiler'
$miriStage = Join-Path $BuildRoot 'miri'
$adapterStage = Join-Path $BuildRoot 'adapter'
New-Item -ItemType Directory -Force -Path $BuildRoot, $compiler, $miriStage, $adapterStage | Out-Null
$marker = Join-Path $compiler '.qfli-rustc-dev-sha256'
$expectedArchive = 'b9914adb9e2d5769fdd49afee5055247fe7673137932f745f594a2f2b9f6e51d'
if (-not (Test-Path -LiteralPath $marker) -or (Get-Content -LiteralPath $marker -Raw).Trim() -ne $expectedArchive) {
  Copy-Item -LiteralPath (Join-Path $Toolchain 'bin') -Destination $compiler -Recurse -Force
  Copy-Item -LiteralPath (Join-Path $Toolchain 'lib') -Destination $compiler -Recurse -Force
  & $PythonExecutable $helper 'unpack-dev' $RustcDevArchive $compiler
  if ($LASTEXITCODE -ne 0) { throw 'Compiler-private component verification/extraction failed.' }
  [IO.File]::WriteAllText($marker, $expectedArchive)
}
Copy-Item -Path (Join-Path $MiriSource '*') -Destination $miriStage -Recurse -Force
Copy-Item -Path (Join-Path $projectRoot 'native/miri_adapter/*') -Destination $adapterStage -Recurse -Force
& $PythonExecutable $helper 'normalize-stage' $miriStage
if ($LASTEXITCODE -ne 0) { throw 'Staged Miri source verification failed.' }
& $PatchExecutable '--fuzz=0' '--no-backup-if-mismatch' '-d' $miriStage '-p1' '-i' `
  (Join-Path $projectRoot 'native/patches/miri-1.98.1-embedded-session.patch')
if ($LASTEXITCODE -ne 0) { throw 'Embedded Miri patch failed.' }

$linker = Join-Path $compiler "lib/rustlib/$hostTriple/bin/rust-lld.exe"
if (-not (Test-Path -LiteralPath $linker)) { throw 'The bundled Rust LLD linker is missing.' }
$environmentNames = @('PATH', 'CARGO_HOME', 'CARGO_TARGET_DIR', 'RUSTC', 'RUSTC_WRAPPER',
  'RUSTC_WORKSPACE_WRAPPER', 'RUSTC_BOOTSTRAP', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS')
$previous = @{}
foreach ($name in $environmentNames) { $previous[$name] = [Environment]::GetEnvironmentVariable($name) }
try {
  $env:PATH = "$(Join-Path $compiler 'bin');$env:PATH"
  if ($CargoHome) { $env:CARGO_HOME = $CargoHome }
  $env:CARGO_TARGET_DIR = Join-Path $BuildRoot 'target'
  $env:RUSTC = Join-Path $compiler 'bin/rustc.exe'
  $env:RUSTC_BOOTSTRAP = '1'
  Remove-Item Env:RUSTC_WRAPPER, Env:RUSTC_WORKSPACE_WRAPPER, Env:RUSTFLAGS -ErrorAction SilentlyContinue
  $env:CARGO_ENCODED_RUSTFLAGS = (@("--sysroot=$compiler", '-Cprefer-dynamic',
    "-Lnative=$(Join-Path $compiler 'bin')", '-Clinker-flavor=ld.lld', "-Clinker=$linker",
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
Write-Output "Adapter: $(Join-Path $BuildRoot "target/$hostTriple/debug/qfli_miri.dll")"
Write-Output "Compiler libraries: $(Join-Path $compiler 'bin')"
