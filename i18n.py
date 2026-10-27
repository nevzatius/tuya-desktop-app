"""Basit çok dilli metin sistemi (Qt Linguist kullanmaz).

    from i18n import tr
    tr("state.on")                          # "Açık" / "On"
    tr("energy.all_lights", cost="₺1,00")   # yer tutuculu metin

Metinler `locales/tr.py` ve `locales/en.py` içindeki `STRINGS` sözlüklerindedir.
Anahtar bir dilde eksikse İngilizceye, o da yoksa anahtarın kendisine düşer.
Dil uygulama açılırken seçilir (`init`); çalışırken değiştirilirse yeni dil bir
sonraki açılışta geçerli olur.
"""

from __future__ import annotations

from locales import en as _en
from locales import tr as _tr

LANGUAGES = {"tr": "Türkçe", "en": "English"}  # dil adları kendi dillerinde yazılır
AUTO = "auto"
SETTINGS_KEY = "language"

_CATALOGS: dict[str, dict[str, str]] = {"tr": _tr.STRINGS, "en": _en.STRINGS}
_language = "en"
_currency = "USD"

# İngilizce arayüzde seçilebilen para birimleri (ISO kodu -> sembol).
CURRENCIES = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "CAD": "CA$",
    "AUD": "A$",
    "CHF": "CHF",
    "INR": "₹",
    "BRL": "R$",
    "TRY": "₺",
}
DEFAULT_CURRENCY = "USD"


def tr(key: str, **values: object) -> str:
    """Anahtarın etkin dildeki metni; `values` ile `{ad}` yer tutucuları doldurulur."""
    text = _CATALOGS[_language].get(key)
    if text is None:
        text = _CATALOGS["en"].get(key, key)
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def language() -> str:
    return _language


def set_language(code: str) -> None:
    global _language
    if code not in _CATALOGS:
        raise ValueError(f"unsupported language: {code!r}")
    _language = code


def system_language(ui_language: str | None = None) -> str:
    """Sistem dili Türkçe ise "tr", değilse "en". `ui_language` testler içindir ("tr-TR" gibi)."""
    name = ui_language if ui_language is not None else _system_ui_language()
    name = name.lower()
    return "tr" if name.startswith(("tr", "turkish")) else "en"


def _system_ui_language() -> str:
    try:
        from PySide6.QtCore import QLocale

        languages = QLocale.system().uiLanguages()
        return languages[0] if languages else QLocale.system().name()
    except Exception:  # noqa: BLE001 - Qt yoksa standart kütüphaneye düş
        import locale

        return locale.getlocale()[0] or ""


def resolve(preference: str | None, ui_language: str | None = None) -> str:
    """Kullanıcı tercihi ("tr", "en", "auto" ya da boş) -> kullanılacak dil."""
    if preference in _CATALOGS:
        return str(preference)
    return system_language(ui_language)


def init(preference: str | None = None, ui_language: str | None = None) -> str:
    code = resolve(preference, ui_language)
    set_language(code)
    return code


def upper(text: str) -> str:
    """Büyük harfe çevirir; Türkçede i -> İ ve ı -> I kuralına uyar."""
    if _language == "tr":
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


# -- para birimi ve sayı biçimi ------------------------------------------------


def system_currency() -> str:
    """Sistem bölgesinin para birimi (listede yoksa USD)."""
    try:
        from PySide6.QtCore import QLocale

        code = QLocale.system().currencySymbol(QLocale.CurrencySymbolFormat.CurrencyIsoCode)
    except Exception:  # noqa: BLE001
        code = ""
    return code if code in CURRENCIES else DEFAULT_CURRENCY


def set_currency(code: str) -> None:
    global _currency
    _currency = code if code in CURRENCIES else DEFAULT_CURRENCY


def currency_code() -> str:
    return _currency


def currency_symbol() -> str:
    """Türkçede her zaman ₺; diğer dillerde seçilen para biriminin sembolü."""
    return CURRENCIES["TRY"] if _language == "tr" else CURRENCIES[_currency]


def format_number(value: float, decimals: int) -> str:
    """Dile uygun sayı: Türkçe 1.234,50 — İngilizce 1,234.50."""
    text = f"{value:,.{decimals}f}"
    if _language == "tr":
        return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return text
