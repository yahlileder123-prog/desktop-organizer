; Per-user installer. Paths are relative to this script.

#define AppName "Desktop Organizer"
#define AppVersion "1.0.0"
#define AppExe "Desktop Organizer.exe"

[Setup]
AppId={{6F4C2A91-8B3E-4D17-9A55-C0E7D2B84F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Desktop Organizer
DefaultDirName={localappdata}\Desktop Organizer
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist
OutputBaseFilename=DesktopOrganizerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: postinstall nowait skipifsilent
