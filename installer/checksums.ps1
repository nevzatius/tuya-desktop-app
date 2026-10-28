# SHA256SUMS.txt yazar. Betikler bunu dot-source eder.
# Cikti "<sha256 kucuk harf>  <dosya adi>" satirlaridir; satir sonu LF, BOM yok, sonda bos satir yok. Boylece
# `sha256sum -c SHA256SUMS.txt` Linux/macOS'ta da calisir (Set-Content CRLF yazar ve -c bunu "dosya yok" sayar).
function Write-Sha256Sums {
    param([Parameter(Mandatory)][string]$Directory)
    $dir = (Resolve-Path $Directory).Path
    $target = Join-Path $dir "SHA256SUMS.txt"
    $lines = Get-ChildItem $dir -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | Sort-Object Name | ForEach-Object {
        "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
    }
    $text = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($target, $text, (New-Object System.Text.UTF8Encoding $false))
}
