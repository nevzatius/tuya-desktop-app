"""Yanıp söndürme (blink_light), sihirbazdaki düğmesi ve gizli bilgi maskeleme."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import light_core as lc
from bleak.exc import BleakError
from privacy import MASK, redact
from tuya_ble_sdk import DataPoint, DataPointType, TuyaBleAuthenticationError

CFG = lc.Config(device_id="d" * 22, local_key="K3yL0cal#abcdef", uuid="u" * 16, name="x", address="AA:BB:CC:DD:EE:FF")


class FakeClient:
    """LightClient'ın blink_light'ın kullandığı yüzeyi."""

    def __init__(self, power, fail_on_call=None, connect_error=None):
        self.state = SimpleNamespace(power=power)
        self.calls: list = []
        self.fail_on_call, self.connect_error = fail_on_call, connect_error

    async def connect(self):
        if self.connect_error:
            raise self.connect_error
        self.calls.append("connect")

    async def set_power(self, on):
        if self.fail_on_call is not None and len([c for c in self.calls if isinstance(c, bool)]) == self.fail_on_call:
            self.fail_on_call = None  # yalnızca bir kez patla
            raise lc.LightNotFound()
        self.calls.append(on)

    async def close(self):
        self.calls.append("close")


def run(client, **kw):
    return asyncio.run(lc.blink_light(CFG, pause=0, state_wait=0.05, client_factory=lambda cfg: client, **kw))


# -- blink_light --------------------------------------------------------------------------


def test_blink_when_on_turns_off_and_on_twice_and_ends_on():
    client = FakeClient(power=True)
    assert run(client) is True
    assert client.calls == ["connect", False, True, False, True, "close"]


def test_blink_when_off_flashes_on_and_ends_off():
    client = FakeClient(power=False)
    assert run(client) is False
    assert client.calls == ["connect", True, False, True, False, "close"]


def test_blink_with_unknown_state_never_leaves_light_dark():
    client = FakeClient(power=None)
    run(client)
    assert client.calls[-2] is True and client.calls[-1] == "close"


def test_blink_restores_original_state_when_interrupted():
    client = FakeClient(power=True, fail_on_call=1)  # ilk "kapat"tan sonra, "aç"ta patlar
    with pytest.raises(lc.LightNotFound):
        run(client)
    assert client.calls == ["connect", False, True, "close"]  # hata sonrası eski duruma (açık) döndürüldü


def test_blink_connection_failure_closes_and_sends_nothing():
    client = FakeClient(power=True, connect_error=lc.LightNotFound())
    with pytest.raises(lc.LightNotFound):
        run(client)
    assert client.calls == ["close"]


def test_blink_client_has_no_listeners_so_energy_log_never_sees_it(monkeypatch):
    created = []
    real = lc.LightClient

    def spy(cfg):
        client = real(cfg)
        created.append(client)
        return client

    async def noop(self):  # bağlanma ve komutlar gerçek istemcide devre dışı
        self._session = SimpleNamespace(connected=True)

    async def send(self, dps):
        pass

    async def close(self):
        pass

    monkeypatch.setattr(real, "connect", noop)
    monkeypatch.setattr(real, "send", send)
    monkeypatch.setattr(real, "close", close)
    asyncio.run(lc.blink_light(CFG, pause=0, state_wait=0.01, client_factory=spy))
    [client] = created
    assert client._on_state is None and client._on_status is None and client._on_log is None


# -- doğru anahtarla el sıkışan ışık bizimdir (find_candidates + LightClient) -----------------


class PickySession:
    good = "BB:BB"
    tried: list[str] = []
    sent: list = []

    def __init__(self, device, creds, listener):
        self.address, self.listener, self.connected = device.address, listener, False

    async def open(self):
        PickySession.tried.append(self.address)
        if self.address != PickySession.good:
            raise TuyaBleAuthenticationError("someone else's light")
        self.connected = True

    async def close(self):
        self.connected = False

    async def request_status(self):
        self.listener([DataPoint(20, DataPointType.BOOLEAN, True, 0.0)])

    async def send_data_points(self, dps):
        PickySession.sent.append(dps[0][2])
        return b""


def test_blink_finds_our_light_among_candidates_by_handshake(monkeypatch):
    PickySession.tried, PickySession.sent = [], []

    async def candidates(cfg, timeout=0):
        return [SimpleNamespace(address=a, name="") for a in ("AA:AA", "BB:BB", "CC:CC")]

    monkeypatch.setattr(lc, "find_candidates", candidates)
    monkeypatch.setattr(lc, "LightSession", PickySession)
    cfg = lc.Config(device_id="d" * 22, local_key="k" * 16, uuid="", name="x")
    assert asyncio.run(lc.blink_light(cfg, pause=0, state_wait=0.5)) is True
    assert PickySession.tried == ["AA:AA", "BB:BB"]  # yanlış ışık reddetti, doğrusu bulundu, CC denenmedi
    assert PickySession.sent == [False, True, False, True]


# -- sihirbaz: yanıp söndür düğmesi ---------------------------------------------------------


def _wizard_imports():
    from PySide6.QtWidgets import QApplication  # noqa: F401

    import test_wizard as tw

    return tw


@pytest.fixture()
def wiz(qapp):
    return _wizard_imports()


from test_ui import qapp, wait_for  # noqa: E402,F401


def make_dialog(wiz, blinker, existing=None, scanner=None, devices=None):
    from ui.setup_dialog import SetupDialog

    d = SetupDialog(
        existing or set(),
        fetcher=lambda a, s, r: (devices or [wiz.found(1), wiz.found(2)], r),
        scanner=scanner or (lambda: []),
        open_url=lambda u: None,
        blinker=blinker,
    )
    wiz.reach_lights(d)
    return d


def test_blink_button_runs_blinker_with_that_lights_config(wiz):
    got = []
    d = make_dialog(wiz, lambda cfg: got.append(cfg.device_id) or True)
    row = d.rows[1]
    assert not row.blink_button.isHidden()
    row.blink_button.click()
    assert wait_for(lambda: "bu ışık bu" in row.status.text())
    assert got == ["dev2"]
    assert wait_for(lambda: d._blink_worker is None and d.scan_button.isEnabled() and row.blink_button.isEnabled())


def test_blink_disables_ble_buttons_while_running(wiz):
    import threading

    release = threading.Event()
    d = make_dialog(wiz, lambda cfg: release.wait(3) or True)
    d.rows[0].blink_button.click()
    assert not d.scan_button.isEnabled() and not d.rows[1].blink_button.isEnabled()
    d.scan_button.click()  # meşgulken yok sayılır
    assert d._scan_worker is None
    d.rows[1].blink_button.click()
    assert d._blinking_row is d.rows[0]
    release.set()
    assert wait_for(lambda: d.scan_button.isEnabled() and d.rows[1].blink_button.isEnabled())


def test_blink_failure_is_shown_with_a_friendly_message(wiz):
    def boom(cfg):
        raise lc.LightNotFound()

    d = make_dialog(wiz, boom)
    d.rows[0].blink_button.click()
    assert wait_for(lambda: "Yanıp söndürülemedi" in d.rows[0].status.text())
    assert "Işık bulunamadı" in d.rows[0].status.text()
    assert wait_for(lambda: d.rows[0].blink_button.isEnabled())


def test_blink_not_offered_for_known_lights_or_non_lights(wiz):
    d = make_dialog(wiz, lambda cfg: True, existing={"dev1"}, devices=[wiz.found(1), wiz.found(2), wiz.found(3, light=False)])
    assert d.rows[0].blink_button.isHidden()  # ekli: uygulama zaten bağlı olabilir
    assert not d.rows[1].blink_button.isHidden()
    assert d.rows[2].blink_button.isHidden()


def test_scan_lists_unmatched_nearby_devices_by_signal_without_addresses(wiz):
    nearby = [
        SimpleNamespace(uuid="u1", rssi=-55, address="AA:BB:CC:DD:EE:01"),
        SimpleNamespace(uuid=None, rssi=-48, address="AA:BB:CC:DD:EE:02"),
        SimpleNamespace(uuid="stranger", rssi=-85, address="AA:BB:CC:DD:EE:03"),
    ]
    d = make_dialog(wiz, lambda cfg: True, scanner=lambda: nearby)
    d.scan_button.click()
    assert wait_for(lambda: d._scan_worker is None and "3" in d.scan_note.text())
    note = d.scan_note.text()
    assert "2 cihaz daha" in note and "güçlü" in note  # en güçlü eşleşmeyen: -48
    assert "AA:BB" not in note and "stranger" not in note  # adres ve kimlik gösterilmez


# -- gizli bilgi maskeleme -------------------------------------------------------------------


def test_redact_known_values_and_patterns():
    text = "dev dddddddddddddddddddddd key K3yL0cal#abcdef mac AA:BB:CC:DD:EE:FF aabbccddeeff guid 123e4567-e89b-12d3-a456-426614174000"
    out = redact(text, [CFG.device_id, CFG.local_key, CFG.address])
    for secret in (CFG.device_id, CFG.local_key, "AA:BB:CC:DD:EE:FF", "aabbccddeeff", "123e4567"):
        assert secret not in out
    assert MASK in out and redact("ok 20 ms", ["ab"]) == "ok 20 ms"  # kısa değerler maskelenmez
    assert redact("aa-bb-cc-dd-ee-ff") == MASK


def test_log_lines_never_contain_identifiers():
    lines = []
    cfg = lc.Config(device_id="d" * 22, local_key="K3yL0cal#abcdef", uuid="uuid-secret-1234", name="x", address="AA:BB:CC:DD:EE:FF")
    client = lc.LightClient(cfg, on_log=lines.append)
    client._log("Send error: device AA:BB:CC:DD:EE:FF key K3yL0cal#abcdef id " + "d" * 22 + " uuid uuid-secret-1234")
    assert lines and all(s not in lines[0] for s in ("AA:BB", "K3yL0cal", "d" * 22, "uuid-secret"))


def test_friendly_error_hides_mac_addresses_from_bleak_errors():
    message = lc.friendly_error(BleakError("Device with address AA:BB:CC:DD:EE:FF was not found"))
    assert "AA:BB:CC" not in message and "Bluetooth" in message
