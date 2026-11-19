; Script generated for Inno Setup 6
; moeDesk Live Wallpaper Application Setup Script

#define MyAppName "moeDesk"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "moeDesk Team"
#define MyAppURL "https://moewalls.com"
#define MyAppExeName "moeDesk.exe"

[Setup]
; App Identity
AppId={{D37F8E41-3A2B-4C9D-9F12-8E3D7B1C90AA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation Directory (Installs for current user or all users cleanly)
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=no

; Output installer executable details
OutputDir=Output
OutputBaseFilename=moeDesk_Setup_v{#MyAppVersion}
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Permissions and Privileges
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Close running instance before upgrade/install
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startupicon"; Description: "Automatically start moeDesk when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Copy all compiled binaries from PyInstaller dist/moeDesk folder
Source: "dist\moeDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu Shortcut
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
; Desktop Shortcut
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon
; Windows Startup Shortcut (if selected)
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: startupicon

[Run]
; Option to launch app after installation completes
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
