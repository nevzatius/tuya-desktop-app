"""Çoklu ışık: sihirbaz, denetleyici, köprüde cihaz değiştirme."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QDialog  # noqa: E402

import cloud_import as ci  # noqa: E402
import devices as dv  # noqa: E402
import light_core as lc  # noqa: E402
from test_ui import FakeBridge, FakeClient, qapp, wait_for  # noqa: E402,F401
from ui.bridge import LightBridge  # noqa: E402
from ui.controller import AppController  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

ID, SECRET = "a" * 20, "b" * 32


def cfg(i: int, name: str | None = None) -> lc.Config:
    return lc.Config(device_id=f"dev{i}", local_key=f"key{i}" * 4, uuid=f"u{i}", name=name or f"Işık {i}")


def found(i: int, light=True, standard=True) -> ci.FoundDevice:
    return ci.FoundDevice(cfg(i), light, standard)


# -- denetleyici ---------------------------------------------------------------------


class SwitchBridge(FakeBridge):
    def __init__(self, first):
        super().__init__()
        self.cfg = first

    def set_device(self, c):
        self.cfg = c
        self.calls.append(("device", c.device_id))

    def release_device(self):
        self.calls.append(("release",))


class FakeDialog:
    DialogCode = QDialog.DialogCode

    def __init__(self, devices, accept=True):
        self._devices, self._accept = devices, accept

    def exec(self):
        return QDialog.DialogCode.Accepted if self._accept else QDialog.DialogCode.Rejected

    def added_devices(self):
        return self._devices


@pytest.fixture()
def env(qapp, tmp_path):
    store = dv.DeviceStore(tmp_path / "devices.json")
    store.add(cfg(1))
    store.add(cfg(2))
    bridge = SwitchBridge(store.current())
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    win = MainWindow(store.current(), bridge, settings=settings, use_tray=False)
    state = {"dialog": FakeDialog([]), "confirm": True, "name": "Salon"}
    ctl = AppController(
        store, bridge, win,
        dialog_factory=lambda existing, parent=None: state["dialog"],
        confirm=lambda parent, text: state["confirm"],
        ask_name=lambda parent, current: state["name"],
    )
    yield store, bridge, win, ctl, state
    win.close()


def menu_texts(win):
    return [a.text() for a in win.device_menu.actions() if a.text()]


def test_menu_lists_devices_and_actions(env):
    store, bridge, win, ctl, _ = env
    assert menu_texts(win) == ["Işık 1", "Işık 2", "Işık ekle…", "Adını değiştir…", "Bu ışığı kaldır"]
    assert win.device_button.text().startswith("Işık 1")


def test_choose_switches_bridge_window_and_persists(env):
    store, bridge, win, ctl, _ = env
    win.deviceChosen.emit("dev2")
    assert bridge.calls[-1] == ("device", "dev2") and win.cfg.device_id == "dev2"
    assert win.device_button.text().startswith("Işık 2") and store.selected == "dev2"
    assert dv.DeviceStore.load(store.path).selected == "dev2"
    n = len(bridge.calls)
    win.deviceChosen.emit("dev2")  # zaten seçili
    win.deviceChosen.emit("yok")
    assert len(bridge.calls) == n


def test_switch_resets_screen_and_clears_error(env):
    store, bridge, win, ctl, _ = env
    bridge.state.emit(lc.LightState(power=True, mode="white", brightness_pct=70, temp_pct=10))
    bridge.error.emit("Eski hata")
    win.deviceChosen.emit("dev2")
    assert win.banner.isHidden() and win.state_label.text() == "—" and win.pill.tone() == "warn"


def test_add_selects_first_new_device(env):
    store, bridge, win, ctl, state = env
    state["dialog"] = FakeDialog([cfg(3, "Mutfak"), cfg(4)])
    win.addRequested.emit()
    assert len(store) == 4 and store.selected == "dev3" and bridge.calls[-1] == ("device", "dev3")
    assert "Mutfak" in menu_texts(win)


def test_add_cancelled_changes_nothing(env):
    store, bridge, win, ctl, state = env
    state["dialog"] = FakeDialog([cfg(3)], accept=False)
    win.addRequested.emit()
    assert len(store) == 2 and bridge.calls == []


def test_add_existing_id_updates_key(env):
    store, bridge, win, ctl, state = env
    new = cfg(2)
    new.local_key = "yeni-anahtar-0000"
    state["dialog"] = FakeDialog([new])
    win.addRequested.emit()
    assert len(store) == 2 and store.get("dev2").local_key == "yeni-anahtar-0000"
    assert bridge.calls[-1] == ("device", "dev2")  # yeni anahtarla yeniden bağlan


def test_rename(env):
    store, bridge, win, ctl, state = env
    win.renameRequested.emit()
    assert store.current().name == "Salon" and win.device_button.text().startswith("Salon")
    assert "Salon" in menu_texts(win)
    state["name"] = "  "
    win.renameRequested.emit()
    state["name"] = None
    win.renameRequested.emit()
    assert store.current().name == "Salon"


def test_remove_moves_to_next_and_respects_cancel(env):
    store, bridge, win, ctl, state = env
    state["confirm"] = False
    win.removeRequested.emit()
    assert len(store) == 2
    state["confirm"] = True
    win.removeRequested.emit()
    assert len(store) == 1 and store.selected == "dev2" and bridge.calls[-1] == ("device", "dev2")
    assert dv.DeviceStore.load(store.path).selected == "dev2"


def test_remove_last_releases_bridge_and_opens_wizard(env):
    store, bridge, win, ctl, state = env
    state["confirm"] = True
    state["dialog"] = FakeDialog([], accept=False)  # sihirbazı kapatır
    win.removeRequested.emit()
    win.removeRequested.emit()
    assert len(store) == 0 and ("release",) in bridge.calls
    assert not win.banner.isHidden() and "Işık ekle" in win.banner.text()
    assert win.device_button.text().startswith("Işık yok") and win.pill.tone() == "idle"
    # sonra eklenince normale döner
    state["dialog"] = FakeDialog([cfg(9, "Yeni")])
    win.addRequested.emit()
    assert store.selected == "dev9" and bridge.calls[-1] == ("device", "dev9") and win.banner.isHidden()


# -- köprüde cihaz değiştirme -----------------------------------------------------------


def test_bridge_switch_device_closes_old_and_connects_new(qapp):
    clients = []

    def factory(c, **kw):
        client = FakeClient(c, **kw)
        clients.append(client)
        return client

    bridge = LightBridge(cfg(1), client_factory=factory, watch_interval=0.05)
    seen = []
    bridge.status.connect(seen.append)
    bridge.start()
    try:
        assert wait_for(lambda: ("connect",) in clients[0].calls)
        bridge.set_device(cfg(2))
        assert wait_for(lambda: len(clients) == 2 and ("close",) in clients[0].calls)
        assert bridge.cfg.device_id == "dev2"
        assert wait_for(lambda: ("connect",) in clients[1].calls)  # izleyici yenisine bağlandı
        bridge.set_power(True)
        assert wait_for(lambda: ("power", True) in clients[1].calls)
        assert ("power", True) not in clients[0].calls
    finally:
        bridge.shutdown()


def test_bridge_old_client_events_are_dropped_after_switch(qapp):
    clients = []

    def factory(c, **kw):
        client = FakeClient(c, **kw)
        client.kw = kw
        clients.append(client)
        return client

    bridge = LightBridge(cfg(1), client_factory=factory)
    got = []
    bridge.status.connect(got.append)
    old_status = clients[0].kw["on_status"]
    bridge.set_device(cfg(2))  # iş parçacığı çalışmıyorken doğrudan değişir
    old_status("ESKİ")
    clients[1].kw["on_status"]("YENİ")
    wait_for(lambda: "YENİ" in got, 1)
    assert "YENİ" in got and "ESKİ" not in got


def test_bridge_release_device_stops_retries(qapp):
    clients = []

    def factory(c, **kw):
        client = FakeClient(c, **kw)
        clients.append(client)
        return client

    bridge = LightBridge(cfg(1), client_factory=factory, watch_interval=0.05)
    bridge.start()
    try:
        assert wait_for(lambda: ("connect",) in clients[0].calls)
        bridge.release_device()
        assert wait_for(lambda: ("close",) in clients[0].calls)
        before = clients[0].calls.count(("connect",))
        import time

        time.sleep(0.3)
        assert clients[0].calls.count(("connect",)) == before
    finally:
        bridge.shutdown()
