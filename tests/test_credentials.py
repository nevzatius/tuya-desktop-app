"""get_credentials.fetch_config testleri (sahte bulut nesnesiyle)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import get_credentials as gc  # noqa: E402
import light_core as lc  # noqa: E402

ID = "bf0123456789abcdefghij"


class FakeCloud:
    def __init__(self, devices, requests=None):
        self._devices = devices
        self._requests = requests or {}
        self.asked: list[str] = []

    def getdevices(self):
        return self._devices

    def cloudrequest(self, url, **_):
        self.asked.append(url)
        return self._requests.get(url, {"success": False})


def test_reads_everything_from_device_list():
    cloud = FakeCloud([{"id": ID, "key": "K" * 16, "uuid": "u" * 16, "name": "Işık", "mac": "AA:BB"}])
    cfg = gc.fetch_config(cloud, ID)
    assert (cfg.local_key, cfg.uuid, cfg.name, cfg.address) == ("K" * 16, "u" * 16, "Işık", "AA:BB")
    assert cfg.dps == lc.DEFAULT_DPS  # specs yoksa standart DP'ler


def test_falls_back_to_device_detail_for_missing_uuid():
    cloud = FakeCloud(
        [{"id": ID, "key": "K" * 16, "name": "x"}],
        {f"/v1.0/devices/{ID}": {"success": True, "result": {"uuid": "z" * 16, "mac": "CC"}}},
    )
    cfg = gc.fetch_config(cloud, ID)
    assert cfg.uuid == "z" * 16 and cfg.address == "CC"
    assert f"/v1.0/devices/{ID}" in cloud.asked


def test_dp_ids_come_from_specifications():
    specs = {
        "success": True,
        "result": {
            "functions": [{"code": "switch_led", "dp_id": 1}, {"code": "bright_value_v2", "dp_id": 3}],
            "status": [{"code": "colour_data_v2", "dp_id": 5}, {"code": "baska", "dp_id": 99}],
        },
    }
    cloud = FakeCloud(
        [{"id": ID, "key": "K" * 16, "uuid": "u" * 16}],
        {f"/v1.1/devices/{ID}/specifications": specs},
    )
    dps = gc.fetch_config(cloud, ID).dps
    assert dps["switch_led"] == 1 and dps["bright_value_v2"] == 3 and dps["colour_data_v2"] == 5
    assert dps["work_mode"] == lc.DEFAULT_DPS["work_mode"] and "baska" not in dps


def test_unknown_device_raises():
    with pytest.raises(RuntimeError, match="hesaptaki cihazlar"):
        gc.fetch_config(FakeCloud([{"id": "baska", "key": "k"}]), ID)


def test_cloud_error_dict_raises():
    with pytest.raises(RuntimeError, match="alınamadı"):
        gc.fetch_config(FakeCloud({"Error": "sign invalid"}), ID)


def test_missing_local_key_raises():
    cloud = FakeCloud([{"id": ID, "uuid": "u"}])
    with pytest.raises(RuntimeError, match="local_key"):
        gc.fetch_config(cloud, ID)


# -- connect_cloud / clean ---------------------------------------------------


class FakeTinytuya:
    """Cloud(...) çağrılarını kaydeder; yalnızca `ok_region` bölgesinde başarılı olur."""

    def __init__(self, ok_region=None):
        self.ok_region = ok_region
        self.tried: list[str] = []
        outer = self

        class Cloud:
            def __init__(self, apiRegion, apiKey, apiSecret, apiDeviceID):
                outer.tried.append(apiRegion)
                self.error = None if apiRegion == outer.ok_region else {"Err": "911", "Payload": "sign invalid"}

        self.Cloud = Cloud


def test_clean_strips_paste_artifacts():
    assert gc.clean("  72e3\x163e30\r\n") == "72e33e30"
    assert gc.clean("`abc123`") == "abc123"


def test_connect_cloud_uses_requested_region_first():
    fake = FakeTinytuya(ok_region="eu")
    cloud, used = gc.connect_cloud(fake, "i" * 20, "s" * 32, "eu", ID)
    assert cloud is not None and used == "eu" and fake.tried == ["eu"]


def test_connect_cloud_falls_back_to_other_regions():
    fake = FakeTinytuya(ok_region="eu-w")
    cloud, used = gc.connect_cloud(fake, "i" * 20, "s" * 32, "eu", ID)
    assert used == "eu-w" and fake.tried[:2] == ["eu", "eu-w"]


def test_connect_cloud_reports_last_error_when_all_fail():
    fake = FakeTinytuya(ok_region=None)
    cloud, error = gc.connect_cloud(fake, "i" * 20, "s" * 32, "eu", ID)
    assert cloud is None and "sign invalid" in error
    assert fake.tried[0] == "eu" and set(fake.tried) == set(gc.REGIONS)
