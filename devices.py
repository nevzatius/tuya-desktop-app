"""Birden çok ışığın saklanması (kullanıcıya özel klasörde `devices.json`).

Dosyada yerel anahtarlar bulunur; yalnızca kullanıcı okuyabilsin diye izinler kısılır.
Eski tek-ışıklı `config.json` varsa ilk açılışta içe aktarılır.
"""

from __future__ import annotations

import filecmp
import json
import logging
import os
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

import light_core as lc
from i18n import tr
from version import DATA_FOLDER, LEGACY_DATA_FOLDERS

APP_FOLDER = DATA_FOLDER
STORE_VERSION = 1
MIGRATED_FILES = ("devices.json", "energy.db", "energy.db-journal", "energy.db-wal", "energy.db-shm")
LOGGER = logging.getLogger("tuya_light.devices")


def data_dir_for(folder: str) -> Path:
    """Windows: %APPDATA%\\<klasör>, macOS: ~/Library/Application Support/<klasör>, Linux: ~/.config/<klasör>."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / folder


def user_data_dir() -> Path:
    """Uygulamanın veri klasörü (version.DATA_FOLDER)."""
    return data_dir_for(APP_FOLDER)


def migrate_legacy_data(new_dir: Path | None = None, legacy_dirs: list[Path] | None = None) -> list[str]:
    """Eski veri klasöründeki ışık anahtarlarını ve enerji kaydını yeni klasöre taşır; taşınan dosya adlarını döndürür.

    Güvenli sıra: dosya yeni klasöre geçici adla kopyalanır, içeriği eskisiyle birebir doğrulanır, yerine konur;
    eski dosya ANCAK ondan sonra silinir. Yeni klasörde zaten aynı adlı dosya varsa dokunulmaz (üzerine yazılmaz).
    Bir adım başarısız olursa eski dosya yerinde kalır, anahtarlar kaybolmaz. Eski klasör boşalırsa kaldırılır.
    """
    new_dir = Path(new_dir) if new_dir is not None else user_data_dir()
    olds = [Path(p) for p in legacy_dirs] if legacy_dirs is not None else [data_dir_for(f) for f in LEGACY_DATA_FOLDERS]
    moved: list[str] = []
    for old in olds:
        if not old.is_dir() or old.resolve() == new_dir.resolve():
            continue
        for name in MIGRATED_FILES:
            source, target = old / name, new_dir / name
            if not source.is_file() or target.exists():
                continue
            temp = target.with_name(target.name + ".migrating")
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
                with os.fdopen(fd, "wb") as out, open(source, "rb") as src:
                    shutil.copyfileobj(src, out)
                if not filecmp.cmp(source, temp, shallow=False):
                    raise OSError("copy does not match the original")
                os.replace(temp, target)
            except OSError:
                LOGGER.warning("could not migrate %s; the old file was left in place", name)
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            moved.append(name)
            try:
                source.unlink()
            except OSError:  # örn. eski sürüm hâlâ açık: kopya güvende, eski dosya kalabilir
                LOGGER.warning("migrated %s but could not remove the old copy", name)
        try:
            old.rmdir()  # yalnızca boşsa kalkar
        except OSError:
            pass
    if moved:
        LOGGER.info("migrated %d file(s) from the previous data folder", len(moved))
    return moved


class StoreError(Exception):
    """devices.json okunamadı/bozuk."""


class DeviceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else user_data_dir() / "devices.json"
        self._devices: dict[str, lc.Config] = {}
        self.selected: str = ""

    # -- okuma / yazma ------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None, legacy_config: Path | None = None) -> DeviceStore:
        store = cls(path)
        if store.path.exists():
            try:
                data = json.loads(store.path.read_text(encoding="utf-8"))
                for item in data.get("devices", []):
                    cfg = _config_from_dict(item)
                    store._devices[cfg.device_id] = cfg
                store.selected = data.get("selected", "")
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise StoreError(tr("error.store_unreadable", path=store.path, error=exc)) from exc
        elif legacy_config is not None and Path(legacy_config).exists():
            try:  # eski tek-ışıklı kurulumdan geçiş
                store.add(lc.Config.load(Path(legacy_config)))
                store.save()
            except lc.ConfigError:
                pass
        if store.selected not in store._devices:
            store.selected = next(iter(store._devices), "")
        return store

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": STORE_VERSION,
            "selected": self.selected,
            "devices": [asdict(c) for c in self._devices.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)  # yarım yazılmış dosya bırakmaz

    # -- cihaz listesi ------------------------------------------------------

    def __len__(self) -> int:
        return len(self._devices)

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices

    def devices(self) -> list[lc.Config]:
        return list(self._devices.values())

    def get(self, device_id: str) -> lc.Config | None:
        return self._devices.get(device_id)

    def current(self) -> lc.Config | None:
        return self._devices.get(self.selected)

    def add(self, cfg: lc.Config) -> None:
        """Ekler; aynı cihaz kimliği varsa günceller (yeniden eşleşince anahtar değişir)."""
        self._devices[cfg.device_id] = cfg
        if not self.selected:
            self.selected = cfg.device_id

    def select(self, device_id: str) -> None:
        if device_id not in self._devices:
            raise KeyError(device_id)
        self.selected = device_id

    def remove(self, device_id: str) -> None:
        self._devices.pop(device_id, None)
        if self.selected == device_id:
            self.selected = next(iter(self._devices), "")

    def rename(self, device_id: str, name: str) -> None:
        if device_id in self._devices and name.strip():
            self._devices[device_id].name = name.strip()


def _config_from_dict(data: dict) -> lc.Config:
    if not data.get("device_id") or not data.get("local_key"):
        raise KeyError(tr("error.store_incomplete"))
    dps = dict(lc.DEFAULT_DPS)
    dps.update({k: int(v) for k, v in (data.get("dps") or {}).items()})
    return lc.Config(
        device_id=data["device_id"],
        local_key=data["local_key"],
        uuid=data.get("uuid", ""),
        name=data.get("name") or tr("device.fallback_name"),
        address=data.get("address", ""),
        dps=dps,
        colour_type=data.get("colour_type", "string"),
        category=data.get("category", ""),
        product_name=data.get("product_name", ""),
        watts=lc._watts(data.get("watts")),
    )
