from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cloud_import as ci  # noqa: E402
import devices as dv  # noqa: E402
import light_core as lc  # noqa: E402


def cfg(i: int = 1, **kw) -> lc.Config:
    return lc.Config(device_id=f"dev{i}", local_key=f"key{i}" * 4, uuid=f"uuid{i}", name=f"Işık {i}", **kw)


# -- DeviceStore ---------------------------------------------------------------


def test_store_roundtrip_and_selection(tmp_path):
    store = dv.DeviceStore(tmp_path / "d" / "devices.json")
    store.add(cfg(1))
    store.add(cfg(2, category="dj", product_name="Tavan"))
    assert store.selected == "dev1" and len(store) == 2
    store.select("dev2")
    store.save()
    loaded = dv.DeviceStore.load(tmp_path / "d" / "devices.json")
    assert [c.device_id for c in loaded.devices()] == ["dev1", "dev2"]
    assert loaded.selected == "dev2" and loaded.current().product_name == "Tavan"
    assert loaded.get("dev1").dps == lc.DEFAULT_DPS


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izinleri")
def test_store_file_is_private(tmp_path):
    store = dv.DeviceStore(tmp_path / "devices.json")
    store.add(cfg())
    store.save()
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_add_same_id_updates_key_and_keeps_order(tmp_path):
    store = dv.DeviceStore(tmp_path / "devices.json")
    store.add(cfg(1))
    store.add(cfg(2))
    updated = cfg(1)
    updated.local_key = "yeni-anahtar-123456"
    store.add(updated)
    assert len(store) == 2 and store.get("dev1").local_key == "yeni-anahtar-123456"
    assert [c.device_id for c in store.devices()] == ["dev1", "dev2"]


def test_remove_moves_selection_and_rename(tmp_path):
    store = dv.DeviceStore(tmp_path / "devices.json")
    for i in (1, 2, 3):
        store.add(cfg(i))
    store.select("dev2")
    store.remove("dev2")
    assert store.selected == "dev1" and "dev2" not in store
    store.rename("dev1", "  Yatak odası ")
    store.rename("dev1", "   ")  # boş ad yok sayılır
    assert store.get("dev1").name == "Yatak odası"
    store.remove("dev1")
    store.remove("dev3")
    assert store.current() is None and store.selected == ""
    store.remove("yok")  # hata vermez


def test_select_unknown_raises(tmp_path):
    with pytest.raises(KeyError):
        dv.DeviceStore(tmp_path / "x.json").select("yok")


def test_load_imports_legacy_config_once(tmp_path):
    legacy = tmp_path / "config.json"
    cfg(7).save(legacy)
    path = tmp_path / "data" / "devices.json"
    store = dv.DeviceStore.load(path, legacy_config=legacy)
    assert store.selected == "dev7" and path.exists()
    legacy.unlink()
    assert dv.DeviceStore.load(path, legacy_config=legacy).selected == "dev7"


def test_load_corrupt_file_starts_empty_with_a_backup(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text("{bozuk", encoding="utf-8")
    store = dv.DeviceStore.load(path)
    assert len(store) == 0 and store.problem and store.recovered_from.exists()
    path.write_text(json.dumps({"devices": [{"device_id": "a"}]}), encoding="utf-8")
    store = dv.DeviceStore.load(path)
    assert len(store) == 0 and store.problem  # eksik alanlı kayıt atlanır (ayrıntılı durumlar: test_corrupt_data.py)


def test_load_missing_file_gives_empty_store(tmp_path):
    store = dv.DeviceStore.load(tmp_path / "yok.json")
    assert len(store) == 0 and store.current() is None


def test_user_data_dir_is_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert dv.user_data_dir() == tmp_path / "TuyaDesktopApp"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert dv.user_data_dir() == tmp_path / "cfg" / "TuyaDesktopApp"


# -- cloud_import ----------------------------------------------------------------

GOOD_ID, GOOD_SECRET = "a" * 20, "b" * 32


class FakeCloud:
    def __init__(self, devices, specs=None, error=None, **kwargs):
        self._devices, self._specs, self.error = devices, specs or {}, error
        self.kwargs = kwargs

    def getdevices(self):
        return self._devices

    def cloudrequest(self, url):
        if url.endswith("/specifications"):
            did = url.split("/")[3]
            return {"success": True, "result": self._specs.get(did, {})}
        return {"success": False}


def factory_for(devices, specs=None, bad_regions=()):
    calls = []

    def factory(**kwargs):
        calls.append(kwargs["apiRegion"])
        err = "sign invalid" if kwargs["apiRegion"] in bad_regions else None
        return FakeCloud(devices, specs, error=err, **kwargs)

    factory.calls = calls
    return factory


def test_validate_and_clean():
    assert ci.clean(" ab​c d\n") == "abcd"
    assert ci.validate_credentials(GOOD_ID, GOOD_SECRET) is None
    assert "20" in ci.validate_credentials("kisa", GOOD_SECRET)
    assert "32" in ci.validate_credentials(GOOD_ID, "kisa")


def test_fetch_lists_lights_first_with_specs():
    devices = [
        {"id": "p1", "name": "Priz", "key": "k" * 16, "category": "cz", "uuid": "u1"},
        {"id": "l1", "name": "Tavan", "key": "m" * 16, "category": "dj", "uuid": "u2", "mac": "AA:BB", "product_name": "YX"},
        {"id": "nokey", "name": "Anahtarsız", "category": "dj"},
    ]
    specs = {"l1": {"functions": [{"code": "switch_led", "dp_id": 1}, {"code": "bright_value_v2", "dp_id": "x"}], "status": []}}
    found, used = ci.fetch(f" {GOOD_ID} ", GOOD_SECRET, "eu", factory_for(devices, specs))
    assert used == "eu"
    assert [d.config.device_id for d in found] == ["l1", "p1"]  # anahtarsız elendi, ışık önce
    light = found[0]
    assert light.is_light and light.is_standard and light.config.address == "AA:BB"
    assert light.config.dps["switch_led"] == 1 and light.config.dps["bright_value_v2"] == 22
    assert not found[1].is_light
    assert found[0].label == "Tavan · YX"


def test_connect_falls_back_to_other_region():
    factory = factory_for([{"id": "l", "key": "k", "category": "dj"}], bad_regions=("eu",))
    found, used = ci.fetch(GOOD_ID, GOOD_SECRET, "eu", factory)
    assert used != "eu" and factory.calls[0] == "eu" and len(found) == 1


def test_all_regions_failing_gives_turkish_message():
    factory = factory_for([], bad_regions=tuple(ci.REGIONS))
    with pytest.raises(ci.CloudError, match="yanlış"):
        ci.fetch(GOOD_ID, GOOD_SECRET, "eu", factory)
    assert len(factory.calls) == len(ci.REGIONS)


def test_bad_lengths_fail_before_any_network_call():
    factory = factory_for([])
    with pytest.raises(ci.CloudError):
        ci.fetch("kisa", GOOD_SECRET, "eu", factory)
    assert factory.calls == []


def test_empty_account_and_error_dict_messages():
    with pytest.raises(ci.CloudError, match="Link App Account"):
        ci.fetch(GOOD_ID, GOOD_SECRET, "eu", factory_for([]))
    with pytest.raises(ci.CloudError, match="Cihaz listesi alınamadı"):
        ci.fetch(GOOD_ID, GOOD_SECRET, "eu", factory_for({"Error": "boom"}))
