# Windows kurulum dosyasini (Setup .exe) uretir. Once build_exe.ps1 calismis olmali (dist\<Slug>\<Slug>.exe).
# Sonuc: dist-installer\<Slug>-Setup-<surum>.exe
# Inno Setup 6 gerekir; yoksa ve choco varsa (CI) kurulur. Elle kurmak icin: https://jrsoftware.org/isinfo.php
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\app_info.ps1"
$info = Get-AppInfo
Set-Location $info.Root

$exe = "dist\$($info.Slug)\$($info.Slug).exe"
if (-not (Test-Path $exe)) { throw "$exe not found. Run build_exe.ps1 first." }

function Find-Iscc {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $dirs = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs")) | Where-Object { $_ }
    foreach ($dir in $dirs) {
        $path = Join-Path $dir "Inno Setup 6\ISCC.exe"
        if (Test-Path $path) { return $path }
    }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc -and (Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Inno Setup with Chocolatey..."
    choco install innosetup -y --no-progress
    $iscc = Find-Iscc
}
if (-not $iscc) { throw "Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isinfo.php" }

Write-Host "Compiling installer $($info.Name) $($info.Version)..."
& $iscc "/DAppName=$($info.Name)" "/DAppVersion=$($info.Version)" "/DAppSlug=$($info.Slug)" `
    "/DDataFolder=$($info.DataFolder)" "/DAppPublisher=$($info.Author)" "/DAppUrl=$($info.Url)" `
    "installer\setup.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed (exit code $LASTEXITCODE)" }

$setup = Get-ChildItem "dist-installer\$($info.Slug)-Setup-$($info.Version).exe" -ErrorAction SilentlyContinue
if (-not $setup) { throw "Setup .exe was not produced" }
Write-Host "Ready: $($setup.FullName)" -ForegroundColor Green
