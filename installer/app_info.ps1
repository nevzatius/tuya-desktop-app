# version.py icindeki uygulama bilgisini okur (surum, ad, exe adi...). Betikler bunu dot-source eder.
function Get-AppInfo {
    param([string]$Root = (Split-Path -Parent $PSScriptRoot))
    $text = Get-Content -Raw -Encoding UTF8 (Join-Path $Root "version.py")
    $read = {
        param($key)
        if ($text -match "(?m)^$key\s*=\s*""([^""]*)""") { return $Matches[1] }
        throw "$key not found in version.py"
    }
    return @{
        Root       = $Root
        Version    = (& $read "__version__")
        Name       = (& $read "APP_NAME")
        Slug       = (& $read "APP_SLUG")
        DataFolder = (& $read "DATA_FOLDER")
        Author     = (& $read "APP_AUTHOR")
        Url        = (& $read "APP_URL")
    }
}
