"""Tanılama raporu (gizli bilgi sızmamalı) ve sorun giderici kartı."""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from bleak.exc import BleakError  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
from tuya_ble_sdk import TuyaBleAuthenticationError, TuyaBleHandshakeTimeoutError  # noqa: E402

import diagnostics as diag  # noqa: E402
import i18n  # noqa: E402
import light_core as lc  # noqa: E402
import version  # noqa: E402
from test_ui import CFG, FakeBridge, FakeClient, qapp, wait_for  # noqa: E402,F401
from ui.bridge import LightBridge  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# Rapora asla girmemesi gereken sahte değerler
FAKE = {
    "local_key": "FAKEKEY#9876543210ab",
    "device_id": "bfFAKEDEVICEID0000001",
    "uuid": "fakeuuid0123456789",
    "address": "AA:BB:CC:DD:EE:FF",
    "name": "Ayşe yatak odası",
    "access_id": "ACCESSIDFAKE0123456A",
    "access_secret": "ACCESSSECRETFAKE0123456789abcdef",
}


def fake_light(i: int = 1, **kw) -> lc.Config:
    suffix = "" if i == 1 else str(i)  # 1. ışık FAKE değerlerinin kendisi; diğerleri farklı değerli
    return lc.Config(
        device_id=FAKE["device_id"] + suffix,
        local_key=FAKE["local_key"] + suffix,
        uuid=FAKE["uuid"] + suffix,
        name=FAKE["name"] + suffix,
        address=FAKE["address"],
        category="dj",
        product_name="Smart bulb",
        **kw,
    )


def leaky_events() -> diag.RecentEvents:
    events = diag.RecentEvents()
    second = fake_light(2)
    values = [*FAKE.values(), second.local_key, second.device_id, second.uuid, second.name]
    for secret in values:
        events.add_error(f"Bluetooth error: device {secret} was not found")
        events.add_log(f"Sent with key {secret} to aabbccddeeff / 123e4567-e89b-12d3-a456-426614174000")
    return events


def assert_clean(report: str):
    second = fake_light(2)
    for label, value in [*FAKE.items(), ("key2", second.local_key), ("id2", second.device_id), ("uuid2", second.uuid), ("name2", second.name)]:
        assert value not in report, f"{label} leaked into the report"
    for part in (FAKE["local_key"], FAKE["device_id"], FAKE["uuid"], "AA:BB:CC", "aabbccddeeff", "123e4567", "Ayşe"):
        assert part not in report, part


# -- rapor ---------------------------------------------------------------------------------


def test_report_contains_versions_and_light_summary_but_no_secrets():
    report = diag.build_report(
        [fake_light(1), fake_light(2)],
        leaky_events(),
        language="tr",
        language_setting="auto",
        connected=False,
        bluetooth="ok",
        extra_secrets=[FAKE["access_id"], FAKE["access_secret"]],
    )
    assert_clean(report)
    assert version.__version__ in report and "Python:" in report and "bleak:" in report and "PySide6 / Qt:" in report
    assert "Lights: 2" in report and "category=dj" in report and "product=Smart bulb" in report
    assert "Language: tr (setting: auto)" in report and "Connected: no" in report and "Bluetooth check: ok" in report
    assert "Recent errors" in report and "Recent log lines" in report


def test_report_redacts_secrets_even_without_known_values():
    """Değer bilinmese bile MAC/GUID/uzun hex kalıpları maskelenir (ör. kütüphane hata metinleri)."""
    events = diag.RecentEvents()
    events.add_error("Device with address 11:22:33:44:55:66 not found; id 0123456789abcdef0123")
    report = diag.build_report([], events)
    assert "11:22:33:44:55:66" not in report and "0123456789abcdef0123" not in report and "Lights: 0" in report


def test_report_for_no_lights_and_no_events():
    report = diag.build_report([])
    assert "- none" in report and "(empty)" in report and "Connected: unknown" in report


def test_recent_events_are_bounded_and_deduplicated():
    events = diag.RecentEvents()
    for i in range(100):
        events.add_log(f"line {i}")
        events.add_error(f"error {i}")
    assert len(events.log) == diag.MAX_LOG_LINES and events.log[-1] == "line 99"
    assert len(events.errors) == diag.MAX_ERRORS
    events2 = diag.RecentEvents()
    events2.add_error("a")
    events2.add_error("a")
    assert list(events2.errors) == ["a"]


def test_report_has_no_light_names_or_addresses_in_any_form():
    cfg = fake_light()
    report = diag.build_report([cfg], leaky_events())
    for forbidden in (cfg.name, cfg.address, cfg.uuid, cfg.local_key, cfg.device_id, cfg.address.replace(":", "")):
        assert forbidden not in report


def test_issue_templates_exist_and_ask_for_the_report():
    bug = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
    assert "Copy diagnostic report" in bug and "Tanılama raporunu kopyala" in bug and "required: true" in bug
    assert re.search(r"id: report\s+attributes:.*?validations:\s+required: true", bug, re.S)
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "device_report.yml").exists()


# -- hata türü ve Bluetooth denetimi -----------------------------------------------------------


def test_error_kinds():
    assert lc.error_kind(lc.LightNotFound()) == "not_found"
    assert lc.error_kind(TuyaBleAuthenticationError("x")) == "auth"
    assert lc.error_kind(TuyaBleHandshakeTimeoutError("x")) == "handshake"
    assert lc.error_kind(BleakError("x")) == "bluetooth" and lc.error_kind(TimeoutError()) == "bluetooth"
    assert lc.error_kind(lc.ConfigError("x")) == "config" and lc.error_kind(ValueError("x")) == "other"


def test_classify_bluetooth_error_only_claims_what_it_knows():
    assert lc.classify_bluetooth_error("Bluetooth device is turned off") == "off"
    assert lc.classify_bluetooth_error("Bluetooth radio is disabled") == "off"
    assert lc.classify_bluetooth_error("No Bluetooth adapters found.") == "missing"
    assert lc.classify_bluetooth_error("something odd happened") == "unknown"


def _scanner(error: Exception | None):
    class FakeScanner:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            if error is not None:
                raise error
            return self

        async def __aexit__(self, *exc):
            return False

    return FakeScanner


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (None, "ok"),
        (BleakError("Bluetooth device is turned off"), "off"),
        (BleakError("No Bluetooth adapters found"), "missing"),
        (BleakError("weird"), "unknown"),
        (RuntimeError("boom"), "unknown"),
    ],
)
def test_check_bluetooth(monkeypatch, error, expected):
    monkeypatch.setattr(lc, "BleakScanner", _scanner(error))
    assert asyncio.run(lc.check_bluetooth(0.01)) == expected


# -- köprü: hata türü sinyali ------------------------------------------------------------------


def test_bridge_emits_problem_kind_after_error(qapp):
    clients = {}

    def factory(cfg, **kw):
        clients["c"] = FakeClient(cfg, **kw)
        return clients["c"]

    bridge = LightBridge(CFG, client_factory=factory, watch_interval=0.05)
    seen: list[tuple[str, str]] = []
    bridge.error.connect(lambda t: seen.append(("error", t)))
    bridge.problem.connect(lambda k: seen.append(("problem", k)))
    try:
        clients["c"].fail = lc.LightNotFound()
        bridge.start(watchdog=False)
        bridge.set_power(True)
        assert wait_for(lambda: len(seen) == 2)
        assert seen[0][0] == "error" and seen[1] == ("problem", "not_found")  # hata metni önce, tür sonra
    finally:
        bridge.shutdown()


# -- sorun giderici kartı (pencerede) -----------------------------------------------------------------


@pytest.fixture()
def win(qapp, tmp_path):
    bridge = FakeBridge()
    settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
    window = MainWindow(CFG, bridge, settings=settings, use_tray=False)
    window.checks = []
    window.opened = []
    window.show_info = lambda text: window.checks.append(("info", text))
    window.open_url = window.opened.append
    window.bluetooth_check = lambda: window.checks.append("bt") or "off"
    yield window, bridge
    window.close()


def not_found(bridge):
    bridge.error.emit(lc.friendly_error(lc.LightNotFound()))
    bridge.problem.emit("not_found")


def card_text(window) -> str:
    return " ".join(label.text() for label in window.trouble.findChildren(QLabel))


def test_not_found_shows_card_with_causes_and_real_bluetooth_check(win):
    window, bridge = win
    assert window.trouble.isHidden()
    not_found(bridge)
    assert not window.trouble.isHidden() and window.banner.isHidden()  # kart bandın yerini alır
    assert wait_for(lambda: window.trouble.bluetooth_state == "off")
    text = window.trouble.bluetooth_label.text()
    assert "Bluetooth kapalı" in text and "Windows ayarlarından" in text
    labels = card_text(window)
    for cause in ("Smart Life", "uzakta ya da kapalı", "başka bir yerde açık"):
        assert cause in labels
    assert "doğrulanmadı" in labels  # dürüst işaret
    assert not window.trouble.settings_button.isHidden()


def test_card_is_in_english_and_lists_causes_in_order(win):
    i18n.set_language("en")
    from ui.trouble import TroubleshootCard

    card = TroubleshootCard()
    card.set_bluetooth_state("missing")
    joined = " ".join(label.text() for label in card.findChildren(QLabel))
    positions = [joined.index(f"{n}. ") for n in ("1", "2", "3", "4")]
    assert positions == sorted(positions) and "No Bluetooth adapter found" in joined and "USB Bluetooth adapter" in joined
    card.set_bluetooth_state("ok")
    assert "adapter works" in card.bluetooth_label.text() and card.settings_button.isHidden()
    card.set_bluetooth_state("unknown")
    assert "Could not check" in card.bluetooth_label.text()


def test_card_does_not_recheck_on_every_repeated_error(win):
    window, bridge = win
    not_found(bridge)
    assert wait_for(lambda: window.trouble.bluetooth_state == "off")
    for _ in range(3):  # izleyici her denemede aynı hatayı yeniden bildirir
        not_found(bridge)
    QApplication.processEvents()
    assert window.checks.count("bt") == 1


def test_retry_reconnects_and_rechecks_bluetooth(win):
    window, bridge = win
    not_found(bridge)
    assert wait_for(lambda: window.trouble.bluetooth_state == "off")
    assert wait_for(lambda: window._bt_worker is None)
    window.trouble.retry_button.click()
    assert ("reconnect",) in bridge.calls
    assert wait_for(lambda: window.checks.count("bt") == 2)
    assert wait_for(lambda: window._bt_worker is None)
    window.bluetooth_check = lambda: "ok"
    window.trouble.recheck_button.click()
    assert wait_for(lambda: window.trouble.bluetooth_state == "ok")


def test_card_buttons_open_settings_and_copy_report(win):
    window, bridge = win
    not_found(bridge)
    window.trouble.settings_button.click()
    assert window.opened == ["ms-settings:bluetooth"]
    window.trouble.report_button.click()
    assert window.checks[-1][0] == "info"
    assert "Diagnostic report" in QApplication.clipboard().text()
    QApplication.clipboard().clear()


def test_card_hides_on_connect_other_errors_and_light_switch(win):
    window, bridge = win
    not_found(bridge)
    bridge.connectedChanged.emit(True)
    assert window.trouble.isHidden()
    not_found(bridge)
    bridge.error.emit("anahtar reddedildi")
    bridge.problem.emit("auth")
    assert window.trouble.isHidden() and not window.banner.isHidden()  # diğer hatalarda yalnızca bant
    not_found(bridge)
    window.set_device(CFG)
    assert window.trouble.isHidden()


def test_bluetooth_check_failure_becomes_unknown(win):
    window, bridge = win

    def boom():
        raise RuntimeError("x")

    window.bluetooth_check = boom
    not_found(bridge)
    assert wait_for(lambda: window.trouble.bluetooth_state == "unknown")


# -- pencere: rapor ve menü ----------------------------------------------------------------------------


def test_window_report_never_leaks_what_the_window_has_seen(win):
    window, bridge = win
    light = fake_light()
    window.set_devices([light], light.device_id)
    for secret in FAKE.values():
        bridge.error.emit(f"Bluetooth error: {secret}")
        bridge.log.emit(f"DP write {secret}")
    bridge.log.emit(f"found {light.address} uuid {light.uuid}")
    bridge.connectedChanged.emit(False)
    report = window.build_report()
    for value in (light.local_key, light.device_id, light.uuid, light.address, light.name):
        assert value not in report
    assert "Lights: 1" in report and "Connected: no" in report


def test_settings_menu_has_report_actions(win):
    window, _ = win
    window.copy_report_action.trigger()
    assert "Diagnostic report" in QApplication.clipboard().text()
    window.report_problem_action.trigger()
    assert window.opened[-1].endswith("/issues/new/choose") and window.opened[-1].startswith(version.APP_URL)
    QApplication.clipboard().clear()


def test_window_report_includes_the_log_file_tail_without_secrets(win, tmp_path, monkeypatch):
    import logging

    import applog

    monkeypatch.setattr(applog, "log_path", lambda: tmp_path / "app.log")
    window, bridge = win
    light = fake_light()
    window.set_devices([light], light.device_id)
    root = logging.getLogger()
    level = root.level
    try:
        applog.setup(secrets=lambda: diag.known_secrets([light]))
        logging.getLogger("tuya_light.test").info("session for %s key %s mac %s", light.device_id, light.local_key, light.address)
    finally:
        applog.shutdown()
        root.setLevel(level)
    report = window.build_report()
    assert "session for" in report and "### Log file" in report
    for value in (light.local_key, light.device_id, light.uuid, light.address, light.name):
        assert value not in report
