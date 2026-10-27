from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings  # noqa: E402

import devices as dv  # noqa: E402
import energy as en  # noqa: E402
import light_core as lc  # noqa: E402
from test_multi import FakeDialog, SwitchBridge, cfg  # noqa: E402,F401
from test_ui import qapp  # noqa: E402,F401
from ui.controller import AppController  # noqa: E402
from ui.energy_page import BarChart, EnergyPage  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

NOW = datetime(2026, 10, 27, 21, 0).timestamp()


def ts(h, d=27):
    return datetime(2026, 10, d, h).timestamp()


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


@pytest.fixture()
def log():
    lg = en.EnergyLog(":memory:", clock=lambda: NOW)
    lg.set_watts("a", 1000, ts(8))
    lg.stop("a", ts(10))  # bugün 2 kWh
    lg.set_watts("a", 1000, ts(8, 26))
    lg.stop("a", ts(9, 26))  # dün 1 kWh
    return lg


def make_page(settings, log):
    page = EnergyPage(settings, log)
    page._clock = lambda: NOW
    page.set_device("a", 9.0)
    return page


def test_page_periods_show_cost_and_duration(qapp, settings, log):
    page = make_page(settings, log)
    assert page.cost_label.text() == en.fmt_money(2 * 3.37)
    assert "2,00 kWh" in page.detail_label.text() and "2 sa" in page.detail_label.text()
    page.period_buttons["week"].click()
    assert page.period_title.text() == "SON 7 GÜN" and page.cost_label.text() == en.fmt_money(3 * 3.37)
    page.period_buttons["month"].click()
    assert page.period_title.text() == "SON 30 GÜN" and len(page.chart._buckets) == 30
    page.period_buttons["day"].click()
    assert len(page.chart._buckets) == 24 and page.chart._current == 21


def test_price_change_recalculates_persists_and_emits(qapp, settings, log):
    page = make_page(settings, log)
    got = []
    page.priceChanged.connect(got.append)
    page.price.setValue(5.0)
    assert page.cost_label.text() == en.fmt_money(10.0) and got == [5.0]
    assert float(settings.value("energy/price")) == 5.0
    again = EnergyPage(settings, log)
    assert again.price.value() == 5.0 and again.price_value == 5.0


def test_bad_saved_price_falls_back_to_default(qapp, settings, log):
    settings.setValue("energy/price", "abc")
    assert EnergyPage(settings, log).price_value == en.DEFAULT_PRICE_TL
    settings.setValue("energy/price", -4)
    assert EnergyPage(settings, log).price_value == en.DEFAULT_PRICE_TL


def test_watts_signal_not_emitted_when_device_switches(qapp, settings, log):
    page = make_page(settings, log)
    got = []
    page.wattsChanged.connect(got.append)
    page.set_device("b", 12.0)
    assert got == [] and page.watts.value() == 12.0
    page.watts.setValue(15.0)
    assert got == [15.0]


def test_without_log_shows_placeholder(qapp, settings):
    page = EnergyPage(settings, None)
    page.refresh()
    assert page.detail_label.text() == "Kayıt yok" and page.chart._buckets == []


def test_all_devices_line_only_when_others_have_usage(qapp, settings, log):
    log.set_watts("b", 1000, ts(8))
    log.stop("b", ts(9))
    page = make_page(settings, log)
    assert not page.all_label.isHidden() and "3,00 kWh" in page.all_label.text()
    page.set_device("zz", 9.0)  # kaydı olmayan ışık
    assert "3,00 kWh" in page.all_label.text()


def test_bar_chart_hit_testing_and_paint(qapp):
    chart = BarChart()
    chart.resize(300, 170)
    chart.set_data([en.Bucket("a", 0, 1, 1.0, 60), en.Bucket("b", 1, 2, 0.0, 0)], 3.37, 0)
    plot = chart._plot()
    assert chart._index_at(plot.left() + 1) == 0 and chart._index_at(plot.right() - 1) == 1
    assert chart._index_at(-50) == -1
    assert not chart.grab().isNull()
    chart.set_data([], 3.37, -1)
    assert not chart.grab().isNull()


# -- pencere ve denetleyici -----------------------------------------------------------


@pytest.fixture()
def env(qapp, tmp_path, log):
    store = dv.DeviceStore(tmp_path / "devices.json")
    store.add(cfg(1))
    store.add(cfg(2))
    bridge = SwitchBridge(store.current())
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    lg = en.EnergyLog(":memory:", clock=lambda: NOW)
    win = MainWindow(store.current(), bridge, settings=settings, use_tray=False, energy_log=lg)
    tracker = en.UsageTracker(lg)
    state = {"dialog": FakeDialog([]), "confirm": True}
    ctl = AppController(
        store, bridge, win, tracker=tracker,
        dialog_factory=lambda existing, parent=None: state["dialog"],
        confirm=lambda parent, text: state["confirm"],
    )
    yield store, bridge, win, ctl, tracker, lg, state
    win.close()


def test_tabs_switch_pages(env):
    _, _, win, *_ = env
    assert win.pages.currentIndex() == 0
    win.tab_energy.click()
    assert win.pages.currentIndex() == 1 and win.tab_energy.isChecked()
    win.tab_control.click()
    assert win.pages.currentIndex() == 0


def test_header_stays_visible_on_both_tabs(env):
    _, _, win, *_ = env
    win.show()
    win.tab_energy.click()
    assert win.device_button.isVisible() and win.pill.isVisible()


def test_state_updates_are_recorded(env):
    store, bridge, win, ctl, tracker, lg, _ = env
    assert tracker.device == "dev1" and tracker.watts == 9.0
    bridge.state.emit(lc.LightState(power=True, mode="white", brightness_pct=100))
    assert lg.is_open("dev1")
    bridge.state.emit(lc.LightState(power=False))
    assert not lg.is_open("dev1")
    bridge.state.emit(lc.LightState(power=True, brightness_pct=100))
    bridge.connectedChanged.emit(False)
    assert not lg.is_open("dev1")


def test_switching_device_moves_tracking_and_energy_page(env):
    store, bridge, win, ctl, tracker, lg, _ = env
    bridge.state.emit(lc.LightState(power=True, brightness_pct=100))
    win.deviceChosen.emit("dev2")
    assert not lg.is_open("dev1") and tracker.device == "dev2"
    assert win.energy._device == "dev2"


def test_changing_watts_saves_to_store_and_applies_immediately(env):
    store, bridge, win, ctl, tracker, lg, _ = env
    bridge.client = type("C", (), {"state": lc.LightState(power=True, mode="white", brightness_pct=100)})()
    bridge.state.emit(bridge.client.state)
    win.energy.watts.setValue(20.0)
    assert store.current().watts == 20.0 and tracker.watts == 20.0
    assert dv.DeviceStore.load(store.path).get("dev1").watts == 20.0
    assert lg._db.execute("SELECT watts FROM segments ORDER BY id DESC LIMIT 1").fetchone()[0] == pytest.approx(20.0)


def test_removing_last_device_releases_tracker(env):
    store, bridge, win, ctl, tracker, lg, state = env
    state["dialog"] = FakeDialog([], accept=False)
    win.removeRequested.emit()
    win.removeRequested.emit()
    assert tracker.device == "" and not lg.is_open("dev1") and not lg.is_open("dev2")


def test_heartbeat_timer_extends_open_segment(env):
    store, bridge, win, ctl, tracker, lg, _ = env
    bridge.state.emit(lc.LightState(power=True, brightness_pct=100))
    assert ctl._beat.isActive() and ctl._beat.interval() == 30_000
    lg.heartbeat(NOW + 600)
    assert lg.total(NOW - 1, NOW + 700, "dev1")[1] == pytest.approx(600, abs=1)
