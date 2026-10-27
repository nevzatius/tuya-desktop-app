# Tuya ışık kontrolü - Windows kurulum betiği
#
# Çalıştırma (PowerShell, bu klasörde):
#   powershell -ExecutionPolicy Bypass -File .\kur.ps1
#
# Ne yapar: Python 3.12+ bulur (yoksa kurmayı önerir), .venv oluşturur,
# bağımlılıkları kurur ve modüllerin yüklendiğini doğrular.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Test-Python([string]$Exe, [string[]]$PyArgs) {
    if (-not (Get-Command $Exe -ErrorAction SilentlyContinue)) { return $false }
    try {
        $out = & $Exe @PyArgs -c "import sys; print(int(sys.version_info >= (3, 12)))" 2>$null
        return (($out | Select-Object -First 1) -eq "1")
    } catch {
        return $false
    }
}

$candidates = @(
    @{ Exe = "py";      PyArgs = @("-3.14") },
    @{ Exe = "py";      PyArgs = @("-3.13") },
    @{ Exe = "py";      PyArgs = @("-3.12") },
    @{ Exe = "python";  PyArgs = @() },
    @{ Exe = "python3"; PyArgs = @() }
)

$py = $null
foreach ($c in $candidates) {
    if (Test-Python $c.Exe $c.PyArgs) { $py = $c; break }
}

if (-not $py) {
    Write-Host "Python 3.12 veya üstü bulunamadı." -ForegroundColor Yellow
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "Python 3.12 winget ile (sadece sizin kullanıcınıza) kurulsun mu? (E/H)"
        if ($answer -match '^[EeYy]') {
            winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
            Write-Host ""
            Write-Host "Kurulum bitti. PowerShell penceresini KAPATIP yeniden açın, sonra bu betiği tekrar çalıştırın." -ForegroundColor Green
        }
    } else {
        Write-Host "https://www.python.org/downloads/ adresinden Python 3.12+ kurun" -ForegroundColor Yellow
        Write-Host "('Add python.exe to PATH' kutusunu işaretleyin), sonra bu betiği tekrar çalıştırın."
    }
    exit 1
}

$pyExe = $py.Exe
$pyArgs = $py.PyArgs
$pyLabel = (@($pyExe) + $pyArgs) -join " "
$pyVersion = & $pyExe @pyArgs -c "import sys; print(sys.version.split()[0])"
Write-Host "Python bulundu: $pyLabel ($pyVersion)" -ForegroundColor Green

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Sanal ortam (.venv) oluşturuluyor..."
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) {
        throw "Sanal ortam oluşturulamadı."
    }
}

Write-Host "Bağımlılıklar kuruluyor (birkaç dakika sürebilir)..."
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Bağımlılıklar kurulamadı." }

& $venvPy -c "import light_core; print('Modüller yüklendi.')"
if ($LASTEXITCODE -ne 0) { throw "Modüller yüklenemedi, yukarıdaki hatayı kontrol edin." }

& $venvPy -c "import tkinter" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "UYARI: tkinter yok, arayüz açılmaz ama komut satırı (app.py on/off...) çalışır." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Kurulum tamam. Sıradaki adımlar (bu klasörde):" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe get_credentials.py   # Access Secret'ı siz girersiniz"
Write-Host "  .\.venv\Scripts\python.exe app.py scan"
Write-Host "  .\.venv\Scripts\python.exe app.py on"
Write-Host "  .\.venv\Scripts\python.exe app.py              # arayüz"
Write-Host ""
Write-Host "Not: Telefondaki Smart Life'ı kapatın ya da telefonun Bluetooth'unu kapatın."
