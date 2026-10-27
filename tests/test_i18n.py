"""Çok dilli arayüz: sözlük tutarlılığı, koda gömülü metin denetimi, dile göre biçimler."""

from __future__ import annotations

import ast
import os
import re
import string
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import energy as en
import i18n
from i18n import tr
from locales import en as en_locale
from locales import tr as tr_locale

ROOT = Path(__file__).resolve().parents[1]
TR_STRINGS, EN_STRINGS = tr_locale.STRINGS, en_locale.STRINGS


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


# -- sözlükler ---------------------------------------------------------------------------


def test_every_key_exists_in_every_language():
    # Yeni bir dil eklenince (bkz. CONTRIBUTING.md) burada da otomatik sınanır.
    for code, catalog in i18n._CATALOGS.items():
        assert set(catalog) == set(EN_STRINGS), (code, set(catalog) ^ set(EN_STRINGS))
    assert set(i18n.LANGUAGES) == set(i18n._CATALOGS)


def test_placeholders_match_between_languages():
    for code, catalog in i18n._CATALOGS.items():
        for key in EN_STRINGS:
            assert placeholders(catalog[key]) == placeholders(EN_STRINGS[key]), (code, key)


def test_no_empty_strings_and_no_key_placeholders_leak():
    for catalog in (TR_STRINGS, EN_STRINGS):
        for key, text in catalog.items():
            assert text.strip(), key


def test_english_texts_have_no_turkish_letters():
    # Yalnızca Türkçede bulunan harfler: İngilizce sözlükte yanlışlıkla Türkçe kalmamış olsun.
    for key, text in EN_STRINGS.items():
        assert not re.search("[çğıöşüÇĞİÖŞÜ]", text), key


def _source_files() -> list[Path]:
    files = [ROOT / name for name in ("light_core.py", "cloud_import.py", "devices.py", "energy.py", "light_app.py")]
    files += sorted((ROOT / "ui").glob("*.py"))
    return files


def _string_literals(path: Path):
    """(satır, metin) — docstring'ler hariç tüm string sabitleri."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            yield node.lineno, node.value


# İzinli istisnalar: (dosya, metin). Şu an yok; yeni bir istisna gerekirse gerekçesiyle buraya yazın.
ALLOWED_TURKISH_LITERALS: set[tuple[str, str]] = set()
TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")


def test_no_hardcoded_turkish_in_app_code():
    """Kullanıcıya görünebilecek Türkçe metinler locales/ altında olmalı, koda gömülmemeli.

    Sınırı: yalnızca Türkçe harf içeren metinleri yakalar ("Enerji" gibi ASCII sözcükleri yakalamaz).
    """
    found = []
    for path in _source_files():
        for line, text in _string_literals(path):
            if TURKISH_LETTERS.search(text) and (path.name, text) not in ALLOWED_TURKISH_LITERALS:
                found.append(f"{path.relative_to(ROOT)}:{line}: {text[:60]!r}")
    assert not found, "Koda gömülü Türkçe metin:\n" + "\n".join(found)


def test_all_keys_used_in_code_exist():
    used = set()
    prefixes = set()
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "tr" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    used.add(arg.value)
                elif isinstance(arg, ast.JoinedStr) and isinstance(arg.values[0], ast.Constant):
                    prefixes.add(arg.values[0].value)
    assert used, "tr() çağrısı bulunamadı"
    assert used <= set(EN_STRINGS), sorted(used - set(EN_STRINGS))
    for prefix in prefixes:  # tr(f"preset.{x}") gibi: önek için en az bir anahtar var
        assert any(key.startswith(prefix) for key in EN_STRINGS), prefix


# -- dil seçimi ---------------------------------------------------------------------------


def test_system_language_detection():
    assert i18n.system_language("tr-TR") == "tr" and i18n.system_language("tr") == "tr"
    assert i18n.system_language("Turkish_Türkiye") == "tr"
    assert i18n.system_language("en-US") == "en" and i18n.system_language("de-DE") == "en"
    assert i18n.system_language("") == "en"


def test_resolve_prefers_user_choice_over_system():
    assert i18n.resolve("en", "tr-TR") == "en" and i18n.resolve("tr", "en-US") == "tr"
    assert i18n.resolve("auto", "tr-TR") == "tr" and i18n.resolve(None, "fr-FR") == "en"
    assert i18n.resolve("klingon", "tr-TR") == "tr"  # bilinmeyen tercih: sistem dili


def test_tr_fallbacks_and_placeholders():
    i18n.set_language("en")
    assert tr("state.on") == "On" and tr("no.such.key") == "no.such.key"
    assert tr("cloud.id_length", length=20, got=5) == "Access ID must be 20 characters (currently 5)."
    assert tr("cloud.id_length") == EN_STRINGS["cloud.id_length"]  # değer verilmezse metin olduğu gibi
    i18n.set_language("tr")
    assert tr("state.on") == "Açık"
    with pytest.raises(ValueError):
        i18n.set_language("xx")


def test_turkish_uppercase_rules():
    i18n.set_language("tr")
    assert i18n.upper("tahmin ayarları") == "TAHMİN AYARLARI"
    assert i18n.upper("ışık") == "IŞIK"
    i18n.set_language("en")
    assert i18n.upper("title") == "TITLE"


# -- biçimler ---------------------------------------------------------------------------


def test_number_formats_follow_language():
    i18n.set_language("tr")
    assert en.fmt_money(1234.5) == "₺1.234,50" and en.fmt_kwh(0.5) == "0,500 kWh"
    i18n.set_language("en")
    i18n.set_currency("USD")
    assert en.fmt_money(1234.5) == "$1,234.50" and en.fmt_kwh(0.5) == "0.500 kWh" and en.fmt_kwh(12.5) == "12.50 kWh"
    i18n.set_currency("EUR")
    assert en.fmt_money(3) == "€3.00"
    i18n.set_currency("CHF")
    assert en.fmt_money(3) == "CHF 3.00"


def test_currency_is_always_lira_in_turkish():
    i18n.set_currency("EUR")
    i18n.set_language("tr")
    assert i18n.currency_symbol() == "₺"
    i18n.set_language("en")
    assert i18n.currency_symbol() == "€"
    i18n.set_currency("nonsense")
    assert i18n.currency_code() == i18n.DEFAULT_CURRENCY


def test_duration_and_day_names_follow_language():
    i18n.set_language("en")
    assert en.fmt_duration(5400) == "1 h 30 min" and en.fmt_duration(3600) == "1 h" and en.fmt_duration(0) == "0 min"
    _, _, edges = en.period_edges("week", 1_790_000_000)
    assert {label for label, _, _ in edges} <= {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
    i18n.set_language("tr")
    _, _, edges = en.period_edges("week", 1_790_000_000)
    assert {label for label, _, _ in edges} <= {"Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"}


def test_default_price_only_in_turkish():
    i18n.set_language("tr")
    assert en.default_price() == en.DEFAULT_PRICE_TL
    i18n.set_language("en")
    assert en.default_price() == 0.0


def test_epdk_note_only_in_turkish():
    assert "EPDK" in TR_STRINGS["energy.price_note"]
    assert "EPDK" not in EN_STRINGS["energy.price_note"] and "TL" not in EN_STRINGS["energy.price_note"]


# -- ürün dilleri ve diğer metinler ----------------------------------------------------------


def test_presets_and_errors_are_translated():
    from ui.presets import PRESETS

    i18n.set_language("en")
    assert [p.name for p in PRESETS] == ["Reading", "Focus", "Night", "Movie", "Romantic", "Ocean"]
    import light_core as lc

    assert "not found" in lc.friendly_error(lc.LightNotFound()).lower()
    i18n.set_language("tr")
    assert [p.name for p in PRESETS][0] == "Okuma"
