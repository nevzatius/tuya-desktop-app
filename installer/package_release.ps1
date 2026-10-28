# Release dosyalarini release-assets\ klasorunde toplar:
#   <Slug>-Setup-<surum>.exe      ana indirme (build_installer.ps1 ile uretilir)
#   <Slug>-portable-<surum>.zip   kurulumsuz surum (dist\<Slug> klasorunun zip'i)
#   SHA256SUMS.txt                ikisinin SHA-256 toplamlari
# Dosya adlarinda yalnizca ASCII karakter vardir. Once build_exe.ps1 ve build_installer.ps1 calismis olmali.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\app_info.ps1"
$info = Get-AppInfo
Set-Location $info.Root

$slug, $version = $info.Slug, $info.Version
if ("$slug$version" -notmatch '^[A-Za-z0-9._-]+$') { throw "Release file names must be ASCII (slug='$slug', version='$version')" }

$setup = "dist-installer\$slug-Setup-$version.exe"
$folder = "dist\$slug"
if (-not (Test-Path $setup)) { throw "$setup not found. Run installer\build_installer.ps1 first." }
if (-not (Test-Path $folder)) { throw "$folder not found. Run build_exe.ps1 first." }

$out = "release-assets"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory $out | Out-Null
Copy-Item $setup $out
$zip = "$out\$slug-portable-$version.zip"
Compress-Archive -Path $folder -DestinationPath $zip

$lines = Get-ChildItem $out -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | Sort-Object Name | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
}
$lines | Set-Content -Encoding ascii "$out\SHA256SUMS.txt"
Get-ChildItem $out | Format-Table Name, Length -AutoSize
