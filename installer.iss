; Process Card 安装程序
; Inno Setup 6 脚本
; 使用 ISCC.exe 编译: ISCC installer.iss

#define MyAppName "Process Card"
#define MyAppVersion "0.5.2"
#define MyAppPublisher "Optic Studio"
#define MyAppURL ""
#define MyAppIcon "Optic_card.ico"
; 安装到程序目录时使用固定文件名（卸载/升级时正确覆盖）
#define MyAppExeName "ProcessCard.exe"
; dist/ 中打包产出的版本号文件名
#define MyAppDistExe "ProcessCard_v" + MyAppVersion + ".exe"

[Setup]
AppId={{8A2B3C4D-5E6F-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=.\installer
OutputBaseFilename=ProcessCard_Setup_{#MyAppVersion}
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
DisableProgramGroupPage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式:"; Flags: checkedonce

[Files]
; 主程序 — 源文件带版本号，安装时重命名为固定名
Source: "dist\{#MyAppDistExe}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion

; 系统配置文件（程序会在此目录读写）
Source: "field_schema.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "export_layout.json"; DestDir: "{app}"; Flags: ignoreversion

; 用户工序模板（用户可编辑）
Source: "manufacturing_process.json"; DestDir: "{app}"; Flags: ignoreversion

; 操作指南文档
Source: "JSON修改操作指南.txt"; DestDir: "{app}"; Flags: ignoreversion

; 图标文件（用于安装程序图标，已嵌入 exe 无需安装）

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\操作指南"; Filename: "{app}\JSON修改操作指南.txt"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "运行 Process Card"; Flags: postinstall nowait skipifsilent

[UninstallRun]

; 清理旧版本版本号命名的 exe 残留
[UninstallDelete]
Type: files; Name: "{app}\ProcessCard_v*.exe"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 安装完成后无需额外操作
  end;
end;
