; PT2VHF ITSM: setup Windows por usuário (não modifica banco SQLite)
#ifndef MyAppVersion
#define MyAppVersion "0.3.0"
#endif

[Setup]
AppId=PT2VHF.ITSM
AppName=PT2VHF ITSM
AppVersion={#MyAppVersion}
AppPublisher=PT2VHF
AppPublisherURL=https://alexpmr.com/projetos/itsm/
DefaultDirName={localappdata}\Programs\PT2VHF ITSM
DefaultGroupName=PT2VHF ITSM
UninstallDisplayIcon={app}\PT2VHF-ITSM.exe
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PT2VHF-ITSM-Windows-x64-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\PT2VHF-ITSM.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\PT2VHF ITSM"; Filename: "{app}\PT2VHF-ITSM.exe"
Name: "{autodesktop}\PT2VHF ITSM"; Filename: "{app}\PT2VHF-ITSM.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Run]
Filename: "{app}\PT2VHF-ITSM.exe"; Description: "Iniciar PT2VHF ITSM"; Flags: nowait postinstall skipifsilent
