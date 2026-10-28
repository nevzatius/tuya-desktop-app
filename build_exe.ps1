# Tek klasörlük Windows uygulaması (<APP_SLUG>.exe, version.py'den) üretir.
# Önce kur.ps1 çalıştırılmış olmalı. Sonuç: dist\<APP_SLUG>\
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
. ".\installer\app_info.ps1"
$info = Get-AppInfo   # ad ve surum version.py'den gelir
$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $py = "python" }  # CI ortamı
    else { Write-Host "Önce kur.ps1 dosyasını çalıştırın." -ForegroundColor Red; exit 1 }
}

# Sürümler sabit: aynı kaynaktan aynı exe çıksın. release.yml PYINSTALLER_VERSION ile aynı değeri verir (testle eşleşir).
$pyInstallerVersion = if ($env:PYINSTALLER_VERSION) { $env:PYINSTALLER_VERSION } else { "6.22.3" }
$pyInstallerHooksVersion = "2026.9"
Write-Host "PyInstaller $pyInstallerVersion kuruluyor..."
& $py -m pip install --quiet "pyinstaller==$pyInstallerVersion" "pyinstaller-hooks-contrib==$pyInstallerHooksVersion"
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller kurulamadı." -ForegroundColor Red; exit 1 }

if (-not (Test-Path "assets\app.ico")) { & $py make_icon.py }

function Invoke-Build([string[]]$extra) {
    & $py -m PyInstaller --noconfirm --clean --noupx --windowed `
        --name $($info.Slug) --icon assets\app.ico `
        --add-data "assets;assets" `
        --collect-all bleak `
        --collect-all tuya_ble_sdk `
        --collect-all tinytuya `
        @extra light_app.py
    return $LASTEXITCODE
}

Write-Host "Derleniyor (birkaç dakika sürebilir)..."
$code = Invoke-Build @("--collect-submodules", "winrt")
if ($code -ne 0) {
    Write-Host "winrt eklemeli derleme başarısız, eklemesiz deneniyor..." -ForegroundColor Yellow
    $code = Invoke-Build @()
}
if ($code -ne 0) { Write-Host "Derleme başarısız oldu." -ForegroundColor Red; exit 1 }

# Işıklar kullanıcıya özel klasörde (%APPDATA%\<DATA_FOLDER>, version.py'de) saklanır; ilk açılışta sihirbaz çıkar.
# Eski tek-ışıklı config.json uygulamanın yanındaysa ilk açılışta otomatik içe aktarılır.
Write-Host ""
Write-Host "Hazır: dist\$($info.Slug)\$($info.Slug).exe" -ForegroundColor Green
Write-Host "Kısayol için: .\kisayol_olustur.ps1"
