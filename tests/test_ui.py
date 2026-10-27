"""Arayüz testleri (ışık gerekmez; Qt "offscreen" modunda çalışır)."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject, QPoint, QSettings, Qt, Signal  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from tuya_ble_sdk import DataPointType, TuyaBleAuthenticationError  # noqa: E402

import light_core as lc  # noqa: E402
from ui import colors  # noqa: E402
from ui.bridge import LightBridge  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.presets import PRESETS  # noqa: E402
from ui.theme import apply_theme  # noqa: E402
from ui.widgets import ColorWheel, GradientSlider, PowerButton, StatusPill  # noqa: E402

CFG = lc.Config(device_id="bf0123456789abcdefghij", local_key="TestKey#0123456!", uuid="0123456789abcdef", name="Test ışığı")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


def wait_for(condition, timeout=3.0):
    end = time.time() + timeout
    app = QApplication.instance()
    while time.time() < end:
        if app is not None:
            app.processEvents()  # iş parçacığından gelen sinyaller ana iş parçacığına kuyruklanır
        if condition():
            return True
        time.sleep(0.02)
    return False


# -- renkler ve hazır ayarlar ---------------------------------------------------


def test_white_rgb_endpoints_and_midpoint():
    assert colors.white_rgb(0) == colors.WARM
    assert colors.white_rgb(50) == colors.NEUTRAL
    assert colors.white_rgb(100) == colors.COOL
    assert colors.white_rgb(-10) == colors.WARM and colors.white_rgb(500) == colors.COOL


def test_hs_rgb_primary_colours():
    assert colors.hs_rgb(0, 1000) == (255, 0, 0)
    assert colors.hs_rgb(120, 1000) == (0, 255, 0)
    assert colors.hs_rgb(240, 1000) == (0, 0, 255)
    assert colors.hs_rgb(360, 1000) == (255, 0, 0)
    assert colors.hs_rgb(77, 0) == (255, 255, 255)


def test_accent_follows_light_state():
    assert colors.accent_for(False, "white", 10, None, None) == colors.OFF
    assert colors.accent_for(None, None, None, None, None) == colors.OFF
    assert colors.accent_for(True, "white", 100, None, None) == colors.COOL
    assert colors.accent_for(True, "white", None, None, None) == colors.WARM
    assert colors.accent_for(True, "colour", None, 120, 1000) == (0, 255, 0)
    # çok soluk renkte vurgu tamamen beyaza kaçmasın
    assert colors.accent_for(True, "colour", None, 120, 0) == colors.hs_rgb(120, 350)


def test_shade_and_hex():
    assert colors.shade((200, 100, 50), 0.5) == (100, 50, 25)
    assert colors.shade((200, 100, 50), 1.0) == (200, 100, 50)
    assert colors.shade((0, 0, 0), 2.0) == (255, 255, 255)
    assert colors.hex_of((255, 136, 0)) == "#FF8800"


def test_presets_are_valid():
    names = [p.name for p in PRESETS]
    assert len(names) == len(set(names)) and len(PRESETS) == 6
    for p in PRESETS:
        assert p.mode in ("white", "colour")
        assert 1 <= p.bright <= 100
        assert 0 <= p.temp <= 100 and 0 <= p.hue <= 360 and 0 <= p.sat <= 1000
        assert len(p.swatch()) == 3
        if p.mode == "colour":
            assert p.sat > 0  # renkli ayarın gri olmaması


# -- bileşenler -------------------------------------------------------------------


def test_slider_click_jumps_and_drag_follows(qapp):
    slider = GradientSlider()
    slider.setRange(0, 100)
    slider.resize(300, 36)
    seen = []
    slider.valueChanged.connect(seen.append)
    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(150, 18))
    assert slider.value() == 50
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(14, 18))
    assert slider.value() == 0 and slider.isSliderDown()
    QTest.mouseMove(slider, QPoint(286, 18))
    assert slider.value() == 100
    QTest.mouseMove(slider, QPoint(900, 18))  # dışarı taşsa da sınırda kalır
    assert slider.value() == 100
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(286, 18))
    assert not slider.isSliderDown()
    assert seen[0] == 50


def test_slider_colour_sampling(qapp):
    slider = GradientSlider([(0.0, (0, 0, 0)), (1.0, (200, 100, 50))])
    assert slider._color_at(0) == (0, 0, 0)
    assert slider._color_at(0.5) == (100, 50, 25)
    assert slider._color_at(1) == (200, 100, 50)


@pytest.mark.parametrize(
    "point, expected_hue, expected_sat",
    [((204, 110), 0, 1000), ((110, 16), 90, 1000), ((16, 110), 180, 1000), ((110, 204), 270, 1000)],
)
def test_wheel_maps_position_to_hue_and_saturation(qapp, point, expected_hue, expected_sat):
    wheel = ColorWheel(220)
    got = []
    wheel.changed.connect(lambda h, s: got.append((h, s)))
    QTest.mouseClick(wheel, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(*point))
    assert got and got[-1] == (expected_hue, expected_sat)


def test_wheel_center_is_white_and_far_clicks_are_ignored(qapp):
    wheel = ColorWheel(220)
    got = []
    wheel.changed.connect(lambda h, s: got.append((h, s)))
    QTest.mouseClick(wheel, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(110, 110))
    assert got[-1][1] == 0
    n = len(got)
    QTest.mouseClick(wheel, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(1, 1))
    assert len(got) == n  # çarkın dışı


def test_wheel_set_hs_clamps_and_released_fires(qapp):
    wheel = ColorWheel(220)
    wheel.set_hs(999, -5)
    assert wheel.hs() == (360, 0)
    released = []
    wheel.released.connect(lambda h, s: released.append((h, s)))
    QTest.mousePress(wheel, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(204, 110))
    QTest.mouseRelease(wheel, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(204, 110))
    assert released == [(0, 1000)]


def test_power_button_state_and_click(qapp):
    button = PowerButton()
    clicks = []
    button.clicked.connect(lambda: clicks.append(1))
    QTest.mouseClick(button, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    assert clicks == [1]
    button.set_state(True, (10, 20, 30))
    button.settle()
    assert button._glow == 1.0 and button._accent == (10, 20, 30)
    button.set_state(False, colors.OFF)
    button.settle()
    assert button._glow == 0.0
    assert button.grab().width() == PowerButton.SIZE  # çizim hata vermiyor


def test_status_pill(qapp):
    pill = StatusPill()
    pill.set_status("Bağlı", "ok")
    short = pill.sizeHint().width()
    pill.set_status("Işık bulunamadı", "bad")
    assert pill.sizeHint().width() > short and pill.tone() == "bad" and pill.text() == "Işık bulunamadı"
    pill.set_status("x", "bilinmeyen-ton")
    assert pill.tone() == "idle"
    assert not pill.grab().isNull()


# -- ana pencere (sahte köprü ile) ---------------------------------------------------


class FakeBridge(QObject):
    state = Signal(object)
    status = Signal(str)
    error = Signal(str)
    log = Signal(str)
    connectedChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.calls: list[tuple] = []

    def set_power(self, on):
        self.calls.append(("power", on))

    def set_brightness(self, pct):
        self.calls.append(("brightness", pct))

    def set_white(self, bright, temp):
        self.calls.append(("white", bright, temp))

    def set_colour(self, hue, sat, bright):
        self.calls.append(("colour", hue, sat, bright))

    def apply_scene(self, preset):
        self.calls.append(("scene", preset.name))

    def refresh(self):
        self.calls.append(("refresh",))

    def reconnect(self):
        self.calls.append(("reconnect",))


@pytest.fixture()
def window(qapp, tmp_path):
    bridge = FakeBridge()
    settings = QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat)
    win = MainWindow(CFG, bridge, settings=settings, use_tray=False)
    win.resize(430, 900)
    yield win, bridge, settings
    win.close()


def test_state_updates_do_not_send_commands(window):
    win, bridge, _ = window
    bridge.state.emit(lc.LightState(power=True, mode="white", brightness_pct=70, temp_pct=100))
    assert bridge.calls == []
    assert win.bright.value() == 70 and win.temp.value() == 100
    assert win.state_label.text() == "Açık" and "%70" in win.sub_label.text()
    assert win.temp_value.text() == "Soğuk"
    assert win.stack.currentIndex() == 0 and win.seg_white.isChecked()
    win.power.settle()
    assert win.power._target == 1.0 and win.power._accent == colors.COOL


def test_colour_state_uses_value_for_brightness_and_shows_wheel(window):
    win, bridge, _ = window
    bridge.state.emit(lc.LightState(power=True, mode="colour", brightness_pct=10, hue=240, sat=1000, val=1000))
    assert bridge.calls == []
    assert win.bright.value() == 100  # renk modunda parlaklık V'den gelir
    assert win.wheel.hs() == (240, 1000) and win.hex_label.text() == "#0000FF"
    assert win.stack.currentIndex() == 1 and win.seg_colour.isChecked()


def test_off_and_unknown_states(window):
    win, bridge, _ = window
    bridge.state.emit(lc.LightState(power=False))
    assert win.state_label.text() == "Kapalı"
    win.power.settle()
    assert win.power._target == 0.0 and win.power._accent == colors.OFF
    bridge.state.emit(lc.LightState())
    assert win.state_label.text() == "—"


def test_power_click_toggles_from_current_state(window):
    win, bridge, _ = window
    win.power.click()  # durum bilinmiyor -> aç
    bridge.state.emit(lc.LightState(power=True))
    win.power.click()
    bridge.state.emit(lc.LightState(power=False))
    win.power.click()
    assert bridge.calls == [("power", True), ("power", False), ("power", True)]


def test_user_changes_send_commands(window):
    win, bridge, _ = window
    win.bright.setValue(33)
    win.temp.setValue(80)
    win.wheel.changed.emit(120, 800)
    assert ("brightness", 33) in bridge.calls
    assert ("white", 33, 80) in bridge.calls
    assert ("colour", 120, 800, 33) in bridge.calls
    assert win.bright_value.text() == "%33"


def test_mode_buttons_send_matching_command(window):
    win, bridge, _ = window
    win.bright.setValue(60)
    bridge.calls.clear()
    win.seg_colour.click()
    assert bridge.calls[-1][0] == "colour" and win.stack.currentIndex() == 1
    win.seg_white.click()
    assert bridge.calls[-1][0] == "white" and win.stack.currentIndex() == 0


def test_preset_updates_controls_and_sends_one_scene(window):
    win, bridge, _ = window
    film = next(b for b in win.preset_buttons if b.property("preset") == "Film")
    film.click()
    assert bridge.calls == [("scene", "Film")]  # tek komut; kaydırıcı değişimi ek komut üretmedi
    assert win.bright.value() == 20 and win.stack.currentIndex() == 1
    assert win.wheel.hs() == (28, 900)
    bridge.calls.clear()
    next(b for b in win.preset_buttons if b.property("preset") == "Odak").click()
    assert bridge.calls == [("scene", "Odak")]
    assert win.temp.value() == 100 and win.stack.currentIndex() == 0


def test_status_pill_error_banner_and_tools(window):
    win, bridge, _ = window
    bridge.status.emit("Bağlı")
    assert win.pill.tone() == "ok"
    bridge.status.emit("Bağlanılıyor…")
    assert win.pill.tone() == "warn"
    bridge.status.emit("Işık bulunamadı")
    assert win.pill.tone() == "bad"
    assert win.banner.isHidden()
    bridge.error.emit("Bir sorun var")
    assert not win.banner.isHidden() and win.banner.text() == "Bir sorun var"
    assert "ERROR: Bir sorun var" in win.log_view.toPlainText()
    bridge.connectedChanged.emit(True)
    assert win.banner.isHidden()
    win.refresh_button.click()
    win.reconnect_button.click()
    assert ("refresh",) in bridge.calls and ("reconnect",) in bridge.calls
    win.log_toggle.setChecked(True)
    assert not win.log_view.isHidden()


def test_close_without_tray_saves_geometry(window):
    win, _, settings = window
    win.close()
    assert settings.contains("geometry")


def test_screenshots_render_without_errors(window):
    win, bridge, _ = window
    win.show()
    bridge.state.emit(lc.LightState(power=True, mode="colour", hue=10, sat=900, val=500))
    assert not win.grab().isNull()


# -- köprü (sahte ışık istemcisi ile) ------------------------------------------------


class FakeClient:
    def __init__(self, cfg, on_state=None, on_status=None, on_log=None):
        self.cfg = cfg
        self.calls: list[tuple] = []
        self.is_connected = False
        self.block = False
        self.release = threading.Event()
        self.fail: Exception | None = None
        self.connect_error: Exception | None = None

    @property
    def connected(self):
        return self.is_connected

    async def _maybe_block(self):
        import asyncio

        while self.block and not self.release.is_set():
            await asyncio.sleep(0.01)

    async def connect(self):
        self.calls.append(("connect",))
        if self.connect_error:
            raise self.connect_error
        self.is_connected = True

    async def set_power(self, on):
        self.calls.append(("power", on))
        if self.fail:
            raise self.fail

    async def set_brightness(self, pct):
        self.calls.append(("brightness", pct))
        await self._maybe_block()

    async def set_white(self, b, t):
        self.calls.append(("white", b, t))

    async def set_colour_hs(self, h, s, b):
        self.calls.append(("colour", h, s, b))

    async def send(self, dps):
        self.calls.append(("send", dps))

    async def refresh(self):
        self.calls.append(("refresh",))

    async def reconnect(self):
        self.calls.append(("reconnect",))
        self.is_connected = True

    async def close(self):
        self.calls.append(("close",))
        self.is_connected = False


@pytest.fixture()
def bridge_env(qapp):
    created = {}

    def factory(cfg, **kwargs):
        created["client"] = FakeClient(cfg, **kwargs)
        return created["client"]

    bridge = LightBridge(CFG, client_factory=factory, watch_interval=0.05)
    events = {"error": [], "connected": []}
    bridge.error.connect(events["error"].append)
    bridge.connectedChanged.connect(events["connected"].append)
    yield bridge, created["client"], events
    bridge.shutdown()


def test_bridge_latest_value_wins(bridge_env):
    bridge, client, _ = bridge_env
    client.block = True
    bridge.start(watchdog=False)
    bridge.set_brightness(1)
    assert wait_for(lambda: ("brightness", 1) in client.calls)  # ilki çalışmaya başladı, bloklu
    for value in (2, 3, 4):
        bridge.set_brightness(value)
    time.sleep(0.1)
    client.release.set()
    assert wait_for(lambda: ("brightness", 4) in client.calls)
    time.sleep(0.1)
    assert [c for c in client.calls if c[0] == "brightness"] == [("brightness", 1), ("brightness", 4)]


def test_bridge_routes_commands_to_client(bridge_env):
    bridge, client, _ = bridge_env
    bridge.start(watchdog=False)
    bridge.set_power(True)
    bridge.set_white(40, 70)
    assert wait_for(lambda: ("power", True) in client.calls and ("white", 40, 70) in client.calls)
    bridge.set_colour(200, 900, 55)  # aynı "light" kanalı: önceki bittikten sonra gönderilirse iletilir
    assert wait_for(lambda: ("colour", 200, 900, 55) in client.calls)


def test_bridge_scene_is_one_frame_with_power_on(bridge_env):
    bridge, client, _ = bridge_env
    bridge.start(watchdog=False)
    film = next(p for p in PRESETS if p.name == "Film")
    bridge.apply_scene(film)
    assert wait_for(lambda: any(c[0] == "send" for c in client.calls))
    dps = next(c[1] for c in client.calls if c[0] == "send")
    assert dps[0] == (CFG.dps["switch_led"], DataPointType.BOOLEAN, True)
    assert (CFG.dps["work_mode"], DataPointType.ENUM, 1) in dps
    assert any(d[0] == CFG.dps["colour_data_v2"] for d in dps)
    white = next(p for p in PRESETS if p.name == "Okuma")
    bridge.apply_scene(white)
    assert wait_for(lambda: sum(c[0] == "send" for c in client.calls) == 2)
    dps = [c[1] for c in client.calls if c[0] == "send"][1]
    assert (CFG.dps["work_mode"], DataPointType.ENUM, 0) in dps and dps[0][2] is True


def test_bridge_reports_errors_in_turkish(bridge_env):
    bridge, client, events = bridge_env
    bridge.start(watchdog=False)
    client.fail = lc.LightNotFound()
    bridge.set_power(True)
    assert wait_for(lambda: events["error"])
    assert "Işık bulunamadı" in events["error"][0]


def test_bridge_watchdog_connects_and_reports(bridge_env):
    bridge, client, events = bridge_env
    bridge.start()
    assert wait_for(lambda: ("connect",) in client.calls)
    assert wait_for(lambda: events["connected"] == [True])
    client.is_connected = False  # bağlantı koptu
    assert wait_for(lambda: events["connected"] == [True, False, True])  # kopma bildirildi, kendiliğinden döndü
    assert client.calls.count(("connect",)) >= 2


def test_bridge_stops_retrying_after_key_rejected_and_manual_reconnect_recovers(bridge_env):
    bridge, client, events = bridge_env
    client.connect_error = TuyaBleAuthenticationError("red")
    bridge.start()
    assert wait_for(lambda: events["error"])
    time.sleep(0.4)  # izleyici izin verseydi onlarca kez deneyecekti
    assert client.calls.count(("connect",)) == 1
    assert "anahtar" in events["error"][0].lower()
    bridge.reconnect()
    assert wait_for(lambda: ("reconnect",) in client.calls)


def test_bridge_shutdown_closes_client_and_thread(qapp):
    created = {}

    def factory(cfg, **kwargs):
        created["client"] = FakeClient(cfg, **kwargs)
        return created["client"]

    bridge = LightBridge(CFG, client_factory=factory, watch_interval=0.05)
    bridge.start()
    assert wait_for(lambda: ("connect",) in created["client"].calls)
    bridge.shutdown()
    assert ("close",) in created["client"].calls
    assert not bridge._thread.is_alive()
    bridge.shutdown()  # ikinci çağrı sorun çıkarmamalı
