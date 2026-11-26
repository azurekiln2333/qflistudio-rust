; Compile only on the Windows GitHub-hosted packaging job.
; package_installer.py supplies every path and version via /D defines.
#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif
#ifndef InstallerBase
  #error InstallerBase is required
#endif
#ifndef AppVersion
  #error AppVersion is required
#endif
#ifndef FileVersion
  #error FileVersion is required
#endif

[Setup]
AppId=com.azurekiln.qfli.rustcore
AppName=QFLIRustCore
AppVersion={#AppVersion}
VersionInfoVersion={#FileVersion}
AppPublisher=QFLI contributors
AppPublisherURL=https://github.com/azurekiln2333/qflistudio-rust
AppSupportURL=https://github.com/azurekiln2333/qflistudio-rust/issues
DefaultDirName={localappdata}\Programs\QFLIRustCore
DefaultGroupName=QFLIRustCore
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#InstallerBase}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UsePreviousAppDir=no
UsePreviousTasks=no
UninstallDisplayIcon={app}\qfli_rust.exe
CloseApplications=no
RestartApplications=no
SetupLogging=yes
; No SignTool is configured. This setup executable is unsigned.

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\QFLIRustCore"; Filename: "{app}\qfli_rust.exe"; WorkingDir: "{app}"

; No [Run] section: installer verification must not launch the application.
