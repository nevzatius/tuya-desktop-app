# Masaüstüne "Odamdaki Işık" kısayolu oluşturur (kur.ps1'den sonra çalıştırın).
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path $here ".venv\Scripts\pythonw.exe"
$exe = Join-Path $here "dist\OdamdakiIsik\OdamdakiIsik.exe"
$icon = Join-Path $here "assets\app.ico"

if (Test-Path $exe) {
    $target = $exe; $arguments = ""
    Write-Host "Derlenmiş uygulama bulundu, kısayol ona bağlanacak."
} elseif (Test-Path $pyw) {
    $target = $pyw; $arguments = "light_app.py"
} else {
    Write-Host "Önce kur.ps1 dosyasını çalıştırın." -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "Odamdaki Işık.lnk"
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $target
$sc.Arguments = $arguments
$sc.WorkingDirectory = $here
$sc.IconLocation = $icon
$sc.Description = "Odamdaki ışığı Bluetooth ile kontrol et"
$sc.Save()
Write-Host "Kısayol oluşturuldu: $link" -ForegroundColor Green
