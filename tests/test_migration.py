"""Eski veri klasörünün (%APPDATA%\\OdamdakiIsik) yenisine taşınması: anahtarlar ve enerji kaydı kaybolmamalı."""

from __future__ import annotations

import filecmp
import os
import sys
from pathlib import Path

import pytest

import devices as dv
import energy as en
import light_core as lc
import version

LIGHT = lc.Config(device_id="d" * 22, local_key="K3yL0cal#abcdef", uuid="u" * 16, name="Salon", address="AA:BB:CC:DD:EE:FF", category="dj")


@pytest.fixture()
def dirs(tmp_path):
    old, new = tmp_path / "OdamdakiIsik", tmp_path / "TuyaDesktopApp"
    old.mkdir()
    return old, new


def seed_old_store(old: Path) -> None:
    store = dv.DeviceStore(old / "devices.json")
    store.add(LIGHT)
    store.save()
    log = en.EnergyLog(old / "energy.db")
    log.set_watts("a", 10, 1_000_000)
    log.stop("a", 1_003_600)
    log.close()


def test_names_come_from_version_and_legacy_folder_is_listed():
    assert version.APP_NAME == "Tuya Desktop App" and version.APP_SLUG == "TuyaDesktopApp"
    assert version.DATA_FOLDER == "TuyaDesktopApp" and "OdamdakiIsik" in version.LEGACY_DATA_FOLDERS
    assert dv.user_data_dir().name == version.DATA_FOLDER


def test_keys_and_energy_log_move_to_new_folder(dirs):
    old, new = dirs
    seed_old_store(old)
    original = (old / "devices.json").read_bytes()
    moved = dv.migrate_legacy_data(new, [old])
    assert sorted(moved) == ["devices.json", "energy.db"]
    assert (new / "devices.json").read_bytes() == original  # birebir aynı
    assert not old.exists()  # boşalan eski klasör kaldırıldı
    store = dv.DeviceStore.load(new / "devices.json")
    cfg = store.current()
    assert (cfg.device_id, cfg.local_key, cfg.uuid, cfg.name) == (LIGHT.device_id, LIGHT.local_key, LIGHT.uuid, "Salon")
    log = en.EnergyLog(new / "energy.db")
    assert log.total(0, 2_000_000)[1] == 3600  # enerji kaydı da geldi
    log.close()


def test_migration_is_idempotent_and_noop_without_legacy_data(dirs):
    old, new = dirs
    assert dv.migrate_legacy_data(new, [old]) == [] and not new.exists()  # eski klasör boş: yeni klasör bile açılmaz
    assert dv.migrate_legacy_data(new, [old.parent / "yok"]) == []
    seed_old_store(old)
    assert dv.migrate_legacy_data(new, [old])
    assert dv.migrate_legacy_data(new, [old]) == []  # ikinci çalıştırma bir şey yapmaz


def test_never_overwrites_files_in_new_folder(dirs):
    old, new = dirs
    seed_old_store(old)
    new.mkdir()
    (new / "devices.json").write_text('{"version": 1, "selected": "", "devices": []}', encoding="utf-8")
    moved = dv.migrate_legacy_data(new, [old])
    assert moved == ["energy.db"]
    assert '"devices": []' in (new / "devices.json").read_text(encoding="utf-8")  # yeni dosya korundu
    assert (old / "devices.json").exists() and old.exists()  # eski anahtar dosyası kaybolmadı


def test_failed_copy_leaves_old_file_in_place(dirs, monkeypatch):
    old, new = dirs
    seed_old_store(old)
    before = (old / "devices.json").read_bytes()
    monkeypatch.setattr(filecmp, "cmp", lambda *a, **k: False)  # doğrulama başarısız
    assert dv.migrate_legacy_data(new, [old]) == []
    assert (old / "devices.json").read_bytes() == before and (old / "energy.db").exists()
    assert not (new / "devices.json").exists() and not list(new.glob("*.migrating"))  # yarım dosya kalmadı


def test_if_old_copy_cannot_be_removed_the_new_copy_is_still_complete(dirs, monkeypatch):
    old, new = dirs
    seed_old_store(old)
    real_unlink = Path.unlink

    def locked(self, *a, **k):
        if self.parent == old:
            raise PermissionError("in use")  # eski sürüm hâlâ açık
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", locked)
    moved = dv.migrate_legacy_data(new, [old])
    assert sorted(moved) == ["devices.json", "energy.db"]
    assert dv.DeviceStore.load(new / "devices.json").current().local_key == LIGHT.local_key
    assert (old / "devices.json").exists()  # eski kopya kaldı, kaybolan yok


def test_same_folder_is_ignored(dirs):
    old, _ = dirs
    seed_old_store(old)
    assert dv.migrate_legacy_data(old, [old]) == [] and (old / "devices.json").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX izinleri")
def test_migrated_key_file_stays_private(dirs):
    old, new = dirs
    seed_old_store(old)
    dv.migrate_legacy_data(new, [old])
    assert (os.stat(new / "devices.json").st_mode & 0o777) == 0o600


def test_default_arguments_use_platform_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    old = tmp_path / "OdamdakiIsik"
    old.mkdir()
    seed_old_store(old)
    assert sorted(dv.migrate_legacy_data()) == ["devices.json", "energy.db"]
    assert (tmp_path / "TuyaDesktopApp" / "devices.json").exists()
