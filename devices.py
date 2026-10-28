"""Birden çok ışığın saklanması (kullanıcıya özel klasörde `devices.json`).

Dosyada yerel anahtarlar bulunur ve ŞİFRELENMEZ. POSIX'te dosya izni 0600'e kısılır; Windows'ta `os.chmod`
yalnızca salt-okunur bayrağını etkiler, erişimi daraltmaz: koruma `%APPDATA%` klasörünün (kullanıcı profili)
varsayılan erişim listesinden gelir.
Eski tek-ışıklı `config.json` varsa ilk açılışta içe aktarılır (`legacy_imported`); dosya otomatik silinmez.
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
import storage
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


class DeviceStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else user_data_dir() / "devices.json"
        self._devices: dict[str, lc.Config] = {}
        self.selected: str = ""
        self.recovered_from: Path | None = None  # dosya bozuksa: yedeğin yolu (yedeklenemediyse None)
        self.problem = False  # dosya bozuktu ya da bazı kayıtlar atlandı
        self.legacy_imported: Path | None = None  # bu yüklemede içe aktarılan eski config.json (kullanıcı silmeyi düşünsün)

    # -- okuma / yazma ------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None, legacy_config: Path | None = None) -> DeviceStore:
        """Bozuk dosya açılışı çökertmez: yedeği alınır, geçerli kayıtlarla (yoksa boş) devam edilir (`problem`)."""
        store = cls(path)
        data, backup, corrupt = storage.load_json(store.path)
        if corrupt:
            store.problem, store.recovered_from = True, backup
        elif data is not None:
            store._read(data)
        elif legacy_config is not None and Path(legacy_config).exists():
            try:  # eski tek-ışıklı kurulumdan geçiş
                store.add(lc.Config.load(Path(legacy_config)))
                store.save()
                store.legacy_imported = Path(legacy_config)
            except lc.ConfigError:
                pass
        if store.selected not in store._devices:
            store.selected = next(iter(store._devices), "")
        return store

    def _read(self, data: object) -> None:
        bad = not isinstance(data, dict)
        items: object = []
        if not bad:
            items = data.get("devices", [])  # type: ignore[union-attr]
            selected = data.get("selected", "")  # type: ignore[union-attr]
            if isinstance(selected, str):
                self.selected = selected
            else:
                bad = True
            if not isinstance(items, list):
                bad, items = True, []
        for item in items:  # type: ignore[attr-defined]
            try:
                cfg = _config_from_dict(item)
            except storage.PARSE_ERRORS:  # eksik/yanlış tipli cihaz atlanır, diğerleri korunur
                bad = True
                continue
            self._devices[cfg.device_id] = cfg
        if bad:
            self.problem, self.recovered_from = True, storage.backup_file(self.path)

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


def load_current_config(path: Path | None = None, legacy_config: Path | None = None) -> lc.Config:
    """Komut satırı araçları için: uygulamanın okuduğu yerden (veri klasöründeki devices.json) seçili ışık;
    yoksa eski `config.json`. İkisi de yoksa `lc.ConfigError`."""
    store = DeviceStore.load(path)
    cfg = store.current()
    if cfg is not None:
        return cfg
    legacy = Path(legacy_config) if legacy_config is not None else lc.CONFIG_PATH
    if legacy.exists():
        return lc.Config.load(legacy)
    raise lc.ConfigError(tr("error.config_missing", name=store.path.name))


def _text(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise TypeError(key)
    return value


def _config_from_dict(data: object) -> lc.Config:
    """Tek cihaz kaydı; eksik ya da yanlış tipliyse ValueError/TypeError (çağıran kaydı atlar)."""
    if not isinstance(data, dict):
        raise TypeError("device")
    device_id, local_key = _text(data, "device_id"), _text(data, "local_key")
    if not device_id or not local_key:
        raise ValueError("device_id/local_key missing")
    raw_dps = data.get("dps")
    if raw_dps is not None and not isinstance(raw_dps, dict):
        raise TypeError("dps")
    dps = dict(lc.DEFAULT_DPS)
    for key, value in (raw_dps or {}).items():
        if isinstance(value, bool):
            raise TypeError("dps")
        dps[key] = int(value)
    return lc.Config(
        device_id=device_id,
        local_key=local_key,
        uuid=_text(data, "uuid"),
        name=_text(data, "name") or tr("device.fallback_name"),
        address=_text(data, "address"),
        dps=dps,
        colour_type=_text(data, "colour_type", "string"),
        category=_text(data, "category"),
        product_name=_text(data, "product_name"),
        watts=lc._watts(data.get("watts")),
    )
