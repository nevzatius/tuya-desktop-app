; Inno Setup 6 betigi. Degerler installer\build_installer.ps1 tarafindan version.py'den /D ile verilir.
; Elle derlemek icin ISCC'ye /DAppName=... /DAppVersion=... /DAppSlug=... /DDataFolder=... gecin.

#ifndef AppName
  #define AppName "Tuya Desktop App"
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppSlug
  #define AppSlug "TuyaDesktopApp"
#endif
#ifndef DataFolder
  #define DataFolder "TuyaDesktopApp"
#endif
#ifndef AppPublisher
  #define AppPublisher "nevzatius"
#endif
#ifndef AppUrl
  #define AppUrl "https://github.com/nevzatius/tuya-desktop-app"
#endif

[Setup]
; Sabit kimlik: guncellemelerin ayni uygulamanin ustune kurulmasini saglar. DEGISTIRMEYIN.
AppId={{4F0404BD-BA14-44CF-8B04-F06316F812AC}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Yonetici yetkisi gerekmez: varsayilan olarak yalnizca bu kullanici icin kurulur.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename={#AppSlug}-Setup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppSlug}.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

; Kurulum dili sistem diline gore secilir (Turkce sistem -> Turkce, digerleri -> Ingilizce); soru sorulmaz.
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[CustomMessages]
english.StartWithWindows=Start {#AppName} when Windows starts (in the system tray)
turkish.StartWithWindows={#AppName} Windows ile birlikte başlasın (sistem tepsisinde)
english.RemoveData=Also delete your saved lights and energy history on this computer?%n%nChoose No if you plan to reinstall.
turkish.RemoveData=Bu bilgisayardaki kayıtlı ışıklarınız ve enerji geçmişiniz de silinsin mi?%n%nYeniden kuracaksanız Hayır'ı seçin.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\{#AppSlug}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppSlug}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppSlug}.exe"; Tasks: desktopicon

[Registry]
; "Windows ile baslat": yalnizca bu kullanici; uygulama --minimized ile tepside acilir. Kaldirinca silinir.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppSlug}.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#AppSlug}.exe"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Kaldirirken kullanici verisi (anahtarlar, enerji kaydi) varsayilan olarak KORUNUR; sessiz kaldirmada da korunur.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#DataFolder}');
    if DirExists(DataDir) then
      if MsgBox(CustomMessage('RemoveData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
