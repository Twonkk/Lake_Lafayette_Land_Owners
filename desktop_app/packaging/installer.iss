#define MyAppName "Lake Lafayette Landowners Association"
#define MyAppVersion "0.1.16"
#define MyAppPublisher "Lake Lafayette Landowners Association"
#define MyAppExeName "LakeLotManager.exe"

[Setup]
AppId={{A6D6E94E-065E-4D2A-97D6-1D7AE6A1B2C5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=LakeLotManagerSetup
Compression=lzma
SolidCompression=yes

[Files]
Source: "..\dist\LakeLotManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
