"""Arayüzün İngilizce modda kurulması; dil menüsü; enerji sekmesinde para birimi ve fiyat."""

from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402

import energy as en  # noqa: E402
import i18n  # noqa: E402
import light_core as lc  # noqa: E402
from test_energy_ui import log, ts  # noqa: E402,F401
from test_ui import CFG, FakeBridge, qapp  # noqa: E402,F401
from ui.energy_page import EnergyPage  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

NOW = datetime(2026, 10, 27, 21, 0).timestamp()


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


@pytest.fixture(autouse=True)
def _fixed_system_currency(monkeypatch):
    """Testler çalıştırılan makinenin bölgesinden bağımsız olsun."""
    monkeypatch.setattr(i18n, "system_currency", lambda: "USD")


def english_page(settings, log):
    i18n.set_language("en")
    page = EnergyPage(settings, log)
    page._clock = lambda: NOW
    page.set_device("a", 9.0)
    return page


# -- ana pencere ----------------------------------------------------------------------------


def test_main_window_in_english(qapp, settings):
    i18n.set_language("en")
    bridge = FakeBridge()
    win = MainWindow(CFG, bridge, settings=settings, use_tray=False)
    try:
        assert win.tab_control.text() == "Control" and win.tab_energy.text() == "Energy"
        assert win.seg_colour.text() == "Color"
        assert [b.text() for b in win.preset_buttons] == ["Reading", "Focus", "Night", "Movie", "Romantic", "Ocean"]
        bridge.state.emit(lc.LightState(power=True, mode="white", brightness_pct=70, temp_pct=100))
        assert win.state_label.text() == "On" and "White light" in win.sub_label.text()
        assert "70%" in win.sub_label.text() and win.bright_value.text() == "70%"
        assert win.temp_value.text() == "Cool"
        bridge.state.emit(lc.LightState(power=False))
        assert win.state_label.text() == "Off"
        bridge.status.emit("Connected")
        assert win.pill.tone() == "ok"
        bridge.status.emit("Connecting…")
        assert win.pill.tone() == "warn"
        win.show_empty()
        assert win.device_button.text().startswith("No light") and win.pill.tone() == "idle"
    finally:
        win.close()


def test_language_menu_saves_choice_and_asks_for_restart(qapp, settings):
    bridge = FakeBridge()
    win = MainWindow(CFG, bridge, settings=settings, use_tray=False)
    shown = []
    win.show_info = shown.append
    try:
        assert set(win.language_actions) == {"auto", "tr", "en"}
        assert win.language_actions["auto"].isChecked()  # kayıt yok: sistem dili
        win.language_actions["en"].trigger()
        assert settings.value(i18n.SETTINGS_KEY) == "en" and len(shown) == 1
        win.language_actions["en"].trigger()  # aynı seçim: tekrar sormaz
        assert len(shown) == 1
        assert i18n.resolve(str(settings.value(i18n.SETTINGS_KEY)), "tr-TR") == "en"
    finally:
        win.close()


def test_language_menu_shows_saved_choice(qapp, settings):
    settings.setValue(i18n.SETTINGS_KEY, "tr")
    win = MainWindow(CFG, FakeBridge(), settings=settings, use_tray=False)
    try:
        assert win.language_actions["tr"].isChecked() and not win.language_actions["auto"].isChecked()
    finally:
        win.close()


# -- enerji sekmesi --------------------------------------------------------------------------


def test_english_price_starts_empty_and_hides_cost(qapp, settings, log):
    page = english_page(settings, log)
    assert page.price_value == 0.0 and page.price.value() == 0.0
    assert page.cost_label.text() == "—"  # fiyat yokken uydurma tutar gösterilmez
    assert "2.00 kWh" in page.detail_label.text() and "2 h on" in page.detail_label.text()
    assert page.period_title.text() == "TODAY"
    assert page.price.specialValueText() == "Not set"
    assert not page.currency.isHidden() or page.currency.parent() is not None
    assert "EPDK" not in "".join(label.text() for label in page.findChildren(type(page.cost_label)))


def test_english_price_and_currency_persist_separately(qapp, settings, log):
    settings.setValue("energy/price", 9.99)  # Türkçe fiyatı İngilizceye sızmamalı
    page = english_page(settings, log)
    assert page.price_value == 0.0
    page.currency.setCurrentIndex(page.currency.findData("EUR"))
    page.price.setValue(0.25)
    assert page.cost_label.text() == "€0.50"  # 2 kWh × 0,25
    assert settings.value("energy/currency") == "EUR" and float(settings.value("energy/price_en")) == 0.25
    assert float(settings.value("energy/price")) == 9.99  # Türkçe fiyat dokunulmadı
    again = english_page(settings, log)
    assert again.price_value == 0.25 and again.currency.currentData() == "EUR" and again.cost_label.text() == "€0.50"


def test_english_week_labels_and_all_lights_line(qapp, settings, log):
    log.set_watts("b", 1000, ts(8))
    log.stop("b", ts(9))
    page = english_page(settings, log)
    assert "All lights:" in page.all_label.text() and "$" not in page.all_label.text()  # fiyat yok: yalnızca kWh
    page.price.setValue(1.0)
    assert page.all_label.text() == "All lights: $3.00 · 3.00 kWh"
    page.period_buttons["week"].click()
    assert page.period_title.text() == "LAST 7 DAYS"
    assert {b.label for b in page.chart._buckets} <= {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


def test_turkish_page_keeps_epdk_note_default_price_and_lira(qapp, settings, log):
    i18n.set_language("tr")
    page = EnergyPage(settings, log)
    page._clock = lambda: NOW
    page.set_device("a", 9.0)
    assert page.price_value == en.DEFAULT_PRICE_TL and page.price.prefix() == "₺ "
    assert page.cost_label.text() == en.fmt_money(2 * 3.37) and page.cost_label.text().startswith("₺")
    notes = " ".join(label.text() for label in page.findChildren(type(page.cost_label)))
    assert "EPDK" in notes
    assert page.price.locale().decimalPoint() == ","


def test_english_default_currency_comes_from_system_region(qapp, settings, log, monkeypatch):
    monkeypatch.setattr(i18n, "system_currency", lambda: "GBP")
    page = english_page(settings, log)
    assert page.currency.currentData() == "GBP" and page.price.prefix() == "£ "
    settings.setValue("energy/currency", "CHF")  # kayıtlı tercih sistemin önüne geçer
    assert english_page(settings, log).currency.currentData() == "CHF"
