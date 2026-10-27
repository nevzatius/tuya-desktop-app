"""Çekirdek katman testleri (gerçek ışık gerekmez).

Çalıştırma:  python -m pytest -q tests
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import light_core as lc  # noqa: E402
from tuya_ble_sdk import (  # noqa: E402
    DataPoint,
    DataPointType,
    TuyaBleAuthenticationError,
    TuyaBleCommandCode,
    TuyaBleConnectionError,
)
from tuya_ble_sdk.commands import parse_data_points  # noqa: E402

CFG = lc.Config(device_id="bf0123456789abcdefghij", local_key="abcdef0123456789", uuid="uuid1234567890ab")


# -- kodlama ---------------------------------------------------------------


def test_encode_roundtrips_through_sdk_parser():
    dps = [
        (20, DataPointType.BOOLEAN, True),
        (21, DataPointType.ENUM, 1),
        (22, DataPointType.VALUE, 500),
        (23, DataPointType.VALUE, -3),
        (24, DataPointType.STRING, "00b403e803e8"),
    ]
    parsed = parse_data_points(lc.encode_data_points(dps), 0, 0.0)
    assert [(p.identifier, p.data_type, p.value) for p in parsed] == dps


def test_encode_exact_bytes():
    assert lc.encode_data_points([(20, DataPointType.BOOLEAN, True)]) == bytes([20, 1, 1, 1])
    assert lc.encode_data_points([(22, DataPointType.VALUE, 1000)]) == bytes([22, 2, 4, 0, 0, 3, 232])
    assert lc.encode_data_points([(21, DataPointType.ENUM, 2)]) == bytes([21, 4, 1, 2])


def test_encode_rejects_oversized_value():
    with pytest.raises(ValueError):
        lc.encode_data_points([(24, DataPointType.STRING, "x" * 300)])


def test_percent_mappings():
    assert lc.pct_to_bright(1) == 10
    assert lc.pct_to_bright(100) == 1000
    assert lc.pct_to_bright(0) == 10 and lc.pct_to_bright(500) == 1000  # sınırlanır
    assert lc.bright_to_pct(10) == 1 and lc.bright_to_pct(1000) == 100
    for pct in range(1, 101):
        assert lc.bright_to_pct(lc.pct_to_bright(pct)) == pct
    assert lc.pct_to_temp(0) == 0 and lc.pct_to_temp(100) == 1000
    assert lc.temp_to_pct(lc.pct_to_temp(37)) == 37


def test_rgb_to_hs():
    assert lc.rgb_to_hs(255, 0, 0) == (0, 1000)
    assert lc.rgb_to_hs(0, 255, 0) == (120, 1000)
    assert lc.rgb_to_hs(0, 0, 255) == (240, 1000)
    assert lc.rgb_to_hs(255, 255, 255) == (0, 0)


def test_hsv_string_roundtrip():
    s = lc.hsv_string(240, 1000, 1000)
    assert s == "00f003e803e8" and len(s) == 12
    assert lc.parse_hsv_string(s) == (240, 1000, 1000)
    assert lc.parse_hsv_string(s.encode()) == (240, 1000, 1000)
    assert lc.parse_hsv_string("zz") is None
    assert lc.hsv_string(999, -5, 5000) == "01680000" + "03e8"  # sınırlanır


def test_commands_use_configured_dp_numbers():
    cfg = lc.Config("d", "k", "u", dps={**lc.DEFAULT_DPS, "switch_led": 1})
    assert lc.cmd_power(cfg, True) == [(1, DataPointType.BOOLEAN, True)]
    white = lc.cmd_white(CFG, 50, 0)
    assert [w[0] for w in white] == [21, 22, 23] and white[0][2] == 0
    colour = lc.cmd_colour(CFG, 120, 1000, 800)
    assert colour[0] == (21, DataPointType.ENUM, 1)
    assert colour[1] == (24, DataPointType.STRING, "007803e80320")
    assert lc.cmd_colour(CFG, 0, 0, 0, colour_type="raw")[1][1] == DataPointType.RAW


def test_state_from_values():
    st = lc.LightState.from_values(
        CFG, {20: True, 21: 1, 22: 1000, 23: 500, 24: "00f003e803e8"}
    )
    assert (st.power, st.mode, st.brightness_pct, st.temp_pct) == (True, "colour", 100, 50)
    assert (st.hue, st.sat, st.val) == (240, 1000, 1000)
    empty = lc.LightState.from_values(CFG, {})
    assert empty.power is None and empty.mode is None


# -- config ----------------------------------------------------------------


def test_config_save_and_load(tmp_path):
    path = tmp_path / "config.json"
    CFG.save(path)
    loaded = lc.Config.load(path)
    assert loaded == CFG


def test_config_missing_and_incomplete(tmp_path):
    with pytest.raises(lc.ConfigError):
        lc.Config.load(tmp_path / "yok.json")
    bad = tmp_path / "c.json"
    bad.write_text('{"device_id": "x"}')
    with pytest.raises(lc.ConfigError):
        lc.Config.load(bad)


# -- oturum (SDK iç metotları taklit edilerek) ------------------------------


def make_session(listener=None):
    creds = lc.TuyaBleCredentials(uuid="u" * 16, device_id="d" * 22, local_key="abcdef0123")
    return lc.LightSession(SimpleNamespace(address="AA:BB", name="x"), creds, listener)


def test_session_sends_data_points_with_right_command():
    session = make_session()
    sent = {}

    async def fake_request(code, data, **kw):
        sent["code"], sent["data"] = code, data
        return SimpleNamespace(data=b"\x00")

    session._async_request = fake_request
    ack = asyncio.run(session.send_data_points([(20, DataPointType.BOOLEAN, True)]))
    assert sent["code"] == TuyaBleCommandCode.SENDER_DATA_POINTS
    assert sent["data"] == bytes([20, 1, 1, 1])
    assert ack == b"\x00"


def test_session_publish_goes_to_listener_not_queue():
    got = []
    session = make_session(got.append)
    dp = DataPoint(20, DataPointType.BOOLEAN, True, 0.0)
    session._publish([dp])
    assert got == [[dp]]
    assert session._reports.empty()


def test_session_not_connected_before_open():
    assert make_session().connected is False


def test_session_open_cleans_up_on_failure():
    session = make_session()
    calls = []

    async def boom():
        raise TuyaBleConnectionError("yok")

    async def disc():
        calls.append("disconnect")

    session._async_connect = boom
    session._async_disconnect = disc
    with pytest.raises(TuyaBleConnectionError):
        asyncio.run(session.open())
    assert calls == ["disconnect"]


# -- LightClient (sahte oturumla) -------------------------------------------


class FakeSession:
    instances: list[FakeSession] = []
    fail_next_sends = 0
    auth_error = False

    def __init__(self, device, creds, listener):
        self.listener = listener
        self.connected = False
        self.sent: list = []
        FakeSession.instances.append(self)

    async def open(self):
        if FakeSession.auth_error:
            raise TuyaBleAuthenticationError("red")
        self.connected = True

    async def close(self):
        self.connected = False

    async def request_status(self):
        self.listener([DataPoint(20, DataPointType.BOOLEAN, False, 0.0)])

    async def send_data_points(self, dps):
        if FakeSession.fail_next_sends > 0:
            FakeSession.fail_next_sends -= 1
            self.connected = False
            raise TuyaBleConnectionError("koptu")
        self.sent.append(dps)
        return b""


@pytest.fixture()
def fake_ble(monkeypatch):
    FakeSession.instances = []
    FakeSession.fail_next_sends = 0
    FakeSession.auth_error = False
    finds = []

    async def fake_find(cfg, timeout=0):
        finds.append(cfg.uuid)
        return [SimpleNamespace(address="AA:BB", name="light")]

    monkeypatch.setattr(lc, "find_candidates", fake_find)
    monkeypatch.setattr(lc, "LightSession", FakeSession)
    return finds


def test_client_connects_once_and_reuses_session(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        await client.set_power(True)
        await client.set_power(False)
        return client

    client = asyncio.run(go())
    assert len(FakeSession.instances) == 1
    assert len(FakeSession.instances[0].sent) == 2
    assert client.state.power is False  # son komut iyimser olarak yansır


def test_client_reconnects_and_retries_after_drop(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        await client.set_power(True)
        FakeSession.fail_next_sends = 1  # ilk gönderim kopar
        await client.set_power(False)

    asyncio.run(go())
    assert len(FakeSession.instances) == 2
    assert FakeSession.instances[1].sent == [lc.cmd_power(CFG, False)]


def test_client_gives_up_after_second_failure(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        FakeSession.fail_next_sends = 2
        await client.set_power(True)

    with pytest.raises(TuyaBleConnectionError):
        asyncio.run(go())


def test_client_does_not_retry_auth_errors(fake_ble):
    async def go():
        FakeSession.auth_error = True
        await lc.LightClient(CFG).set_power(True)

    with pytest.raises(TuyaBleAuthenticationError):
        asyncio.run(go())
    assert len(FakeSession.instances) == 1


def test_client_raises_when_light_not_found(monkeypatch):
    async def none_found(cfg, timeout=0):
        return []

    monkeypatch.setattr(lc, "find_candidates", none_found)
    with pytest.raises(lc.LightNotFound):
        asyncio.run(lc.LightClient(CFG).set_power(True))
    assert "bulunamadı" in lc.friendly_error(lc.LightNotFound())


def test_brightness_in_colour_mode_keeps_hue(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        await client.connect()
        FakeSession.instances[0].listener(
            [
                DataPoint(21, DataPointType.ENUM, 1, 0.0),
                DataPoint(24, DataPointType.STRING, "007803e803e8", 0.0),
            ]
        )
        await client.set_brightness(50)
        return FakeSession.instances[0].sent[-1]

    sent = asyncio.run(go())
    assert sent[1][2] == lc.hsv_string(120, 1000, lc.pct_to_bright(50))


def test_brightness_in_white_mode_uses_bright_dp(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        await client.set_brightness(30)
        return FakeSession.instances[0].sent[-1]

    assert asyncio.run(go()) == lc.cmd_brightness(CFG, 30)


def test_state_callback_fires_on_device_report(fake_ble):
    states = []

    async def go():
        client = lc.LightClient(CFG, on_state=states.append)
        await client.connect()

    asyncio.run(go())
    assert states and states[-1].power is False


# -- reklam birleştirme ve cihaz bulma -----------------------------------------

from hashlib import md5  # noqa: E402

from tuya_ble_sdk.crypto import encrypt  # noqa: E402

LIGHT_UUID = "0123456789abcdef"


def tuya_adv_parts(uuid: str, product: bytes = b"obfuscated-bytes", bound: bool = True):
    """(servis verisi, üretici verisi): ikisi de ayrı paketlerde gelebilir."""
    key = md5(product).digest()
    service = {lc.SERVICE_UUID: b"\x00" + product}
    manufacturer = {0x07D0: bytes([0x80 if bound else 0, 3, 0, 0, 0, 0]) + encrypt(key, key, uuid.encode())}
    return service, manufacturer


def adv(service=None, manufacturer=None, rssi=-60, uuids=None):
    return SimpleNamespace(
        service_data=service or {},
        manufacturer_data=manufacturer or {},
        service_uuids=uuids or [],
        rssi=rssi,
        local_name=None,
    )


def dev(address="AA:BB:CC:DD:EE:01", name=None):
    return SimpleNamespace(address=address, name=name)


class FakeScanner:
    script: list = []

    def __init__(self, detection_callback=None, **_):
        self.callback = detection_callback

    async def __aenter__(self):
        loop = asyncio.get_running_loop()
        for delay, device, advertisement in FakeScanner.script:
            loop.call_later(delay, self.callback, device, advertisement)
        return self

    async def __aexit__(self, *_):
        return False


@pytest.fixture()
def scanner(monkeypatch):
    monkeypatch.setattr(lc, "BleakScanner", FakeScanner)
    FakeScanner.script = []
    return FakeScanner


def test_tracker_merges_split_advertisements():
    service, manufacturer = tuya_adv_parts(LIGHT_UUID)
    tracker = lc.AdvertisementTracker()
    device = dev()
    first = tracker.feed(device, adv(manufacturer=manufacturer))  # sadece üretici verisi
    assert first is None  # henüz Tuya olduğu anlaşılmadı
    info = tracker.feed(device, adv(service=service))  # servis verisi sonra geldi
    assert info is not None and info.uuid == LIGHT_UUID and info.bound is True
    again = tracker.feed(device, adv())  # boş paket bilgiyi silmemeli
    assert again.uuid == LIGHT_UUID


def test_tracker_ignores_non_tuya_devices():
    tracker = lc.AdvertisementTracker()
    assert tracker.feed(dev("AA:AA"), adv(service={"0000180f-0000-1000-8000-00805f9b34fb": b"\x01"})) is None
    assert tracker.devices() == []


def test_scan_reports_uuid_even_when_packets_are_split(scanner):
    service, manufacturer = tuya_adv_parts(LIGHT_UUID)
    scanner.script = [(0.0, dev(), adv(service=service)), (0.05, dev(), adv(manufacturer=manufacturer))]
    found = asyncio.run(lc.scan_tuya_devices(0.4))
    assert len(found) == 1 and found[0].uuid == LIGHT_UUID
    assert found[0].service_hex and found[0].manufacturer_hex


def test_find_device_matches_uuid_from_split_packets(scanner):
    service, manufacturer = tuya_adv_parts(LIGHT_UUID)
    target = dev()
    scanner.script = [(0.0, dev("11:11"), adv(*tuya_adv_parts("ffffffffffffffff"))), (0.05, target, adv(service=service)), (0.1, target, adv(manufacturer=manufacturer))]
    got = asyncio.run(lc.find_device(CFG_LIGHT(), timeout=2, patience=1))
    assert got is target


def CFG_LIGHT(**overrides):
    base = dict(device_id="bf0123456789abcdefghij", local_key="TestKey#0123456!", uuid=LIGHT_UUID)
    base.update(overrides)
    return lc.Config(**base)


def test_find_device_matches_by_address(scanner):
    service, manufacturer = tuya_adv_parts("ffffffffffffffff")  # farklı uuid
    target = dev("AA:BB:CC:DD:EE:01")
    scanner.script = [(0.0, target, adv(service=service, manufacturer=manufacturer))]
    got = asyncio.run(lc.find_device(CFG_LIGHT(address="aa-bb-cc-dd-ee-01"), timeout=2, patience=5))
    assert got is target


def test_find_device_falls_back_to_the_only_unidentified_tuya_device(scanner):
    service, _ = tuya_adv_parts(LIGHT_UUID)
    target = dev()
    scanner.script = [(0.0, target, adv(service=service))]  # üretici verisi hiç gelmiyor: uuid çözülemez
    got = asyncio.run(lc.find_device(CFG_LIGHT(), timeout=2, patience=0.3))
    assert got is target


def test_find_device_does_not_guess_when_another_known_tuya_device_is_around(scanner):
    other_service, other_manufacturer = tuya_adv_parts("ffffffffffffffff")
    unknown_service, _ = tuya_adv_parts(LIGHT_UUID)
    scanner.script = [
        (0.0, dev("22:22"), adv(service=other_service, manufacturer=other_manufacturer)),
        (0.0, dev("33:33"), adv(service=unknown_service)),
    ]
    assert asyncio.run(lc.find_device(CFG_LIGHT(), timeout=0.8, patience=0.2)) is None


def test_find_device_returns_none_when_nothing_is_seen(scanner):
    assert asyncio.run(lc.find_device(CFG_LIGHT(), timeout=0.5, patience=0.2)) is None


def test_find_device_without_uuid_or_address_takes_first_tuya_device(scanner):
    service, manufacturer = tuya_adv_parts("ffffffffffffffff")
    target = dev()
    scanner.script = [(0.0, target, adv(service=service, manufacturer=manufacturer))]
    got = asyncio.run(lc.find_device(CFG_LIGHT(uuid=""), timeout=2))
    assert got is target


# -- LightClient.connected / set_colour_hs / app_dir -------------------------------


def test_client_connected_property_and_colour_hs(fake_ble):
    async def go():
        client = lc.LightClient(CFG)
        before = client.connected
        await client.set_colour_hs(120, 900, 40)
        sent = FakeSession.instances[0].sent[-1]
        return before, client.connected, sent

    before, after, sent = asyncio.run(go())
    assert before is False and after is True
    assert sent == lc.cmd_colour(CFG, 120, 900, lc.pct_to_bright(40))


def test_app_dir_points_next_to_executable_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "TuyaDesktopApp.exe"))
    assert lc.app_dir() == tmp_path.resolve()


# -- birden çok aday (aynı modelden birkaç ışık) -----------------------------------


def test_find_candidates_orders_unidentified_by_signal_strength(scanner):
    service, _ = tuya_adv_parts(LIGHT_UUID)
    near, far, mid = dev("11:11"), dev("22:22"), dev("33:33")
    scanner.script = [
        (0.0, far, adv(service=service, rssi=-90)),
        (0.0, near, adv(service=service, rssi=-40)),
        (0.0, mid, adv(service=service, rssi=-70)),
    ]
    got = asyncio.run(lc.find_candidates(CFG_LIGHT(), timeout=2, patience=0.3))
    assert got == [near, mid, far]


def test_find_candidates_limits_guesses(scanner):
    service, _ = tuya_adv_parts(LIGHT_UUID)
    scanner.script = [(0.0, dev(f"{i:02d}:00"), adv(service=service, rssi=-40 - i)) for i in range(6)]
    got = asyncio.run(lc.find_candidates(CFG_LIGHT(), timeout=2, patience=0.3))
    assert len(got) == lc.MAX_GUESSES


def test_find_candidates_exact_uuid_match_is_single(scanner):
    service, manufacturer = tuya_adv_parts(LIGHT_UUID)
    target = dev("44:44")
    scanner.script = [
        (0.0, dev("55:55"), adv(service=service, rssi=-30)),
        (0.05, target, adv(service=service, manufacturer=manufacturer, rssi=-80)),
    ]
    assert asyncio.run(lc.find_candidates(CFG_LIGHT(), timeout=2, patience=5)) == [target]


class PickySession(FakeSession):
    """Yalnızca `good` adresli cihaz anahtarımızı kabul eder."""

    good = "BB:BB"
    tried: list[str] = []

    def __init__(self, device, creds, listener):
        super().__init__(device, creds, listener)
        self.address = device.address

    async def open(self):
        PickySession.tried.append(self.address)
        if self.address != PickySession.good:
            raise TuyaBleAuthenticationError("başkasının ışığı")
        self.connected = True


def test_client_tries_next_candidate_until_handshake_succeeds(monkeypatch):
    PickySession.tried = []
    PickySession.instances = []

    async def candidates(cfg, timeout=0):
        return [SimpleNamespace(address=a, name="") for a in ("AA:AA", "BB:BB", "CC:CC")]

    monkeypatch.setattr(lc, "find_candidates", candidates)
    monkeypatch.setattr(lc, "LightSession", PickySession)
    cfg = CFG_LIGHT()

    async def go():
        client = lc.LightClient(cfg)
        await client.connect()
        return client.connected

    assert asyncio.run(go()) is True
    assert PickySession.tried == ["AA:AA", "BB:BB"]  # CC denenmedi
    assert cfg.address == "BB:BB"  # sonraki seferde doğrudan adresle bulunur


def test_client_reports_auth_error_when_no_candidate_accepts_key(monkeypatch):
    PickySession.tried = []
    PickySession.good = "ZZ:ZZ"

    async def candidates(cfg, timeout=0):
        return [SimpleNamespace(address=a, name="") for a in ("AA:AA", "BB:BB")]

    monkeypatch.setattr(lc, "find_candidates", candidates)
    monkeypatch.setattr(lc, "LightSession", PickySession)
    try:
        with pytest.raises(TuyaBleAuthenticationError):
            asyncio.run(lc.LightClient(CFG_LIGHT()).connect())
        assert PickySession.tried == ["AA:AA", "BB:BB"]
    finally:
        PickySession.good = "BB:BB"
