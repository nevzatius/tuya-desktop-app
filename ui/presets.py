"""Tek dokunuşla uygulanan hazır ışık ayarları: 6 yerleşik ayar + kullanıcının kendi ayarları (`presets.json`)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path

import storage
from i18n import tr

from .colors import RGB, hs_rgb, white_rgb

USER_PREFIX = "u-"  # kullanıcı ayarlarının kimliği; yerleşiklerden ayırt eder
MAX_NAME = 24
MAX_USER_PRESETS = 40
STORE_VERSION = 1


@dataclass(frozen=True)
class Preset:
    key: str  # kararlı kimlik ("reading", kullanıcı ayarında "u-1a2b3c4d"); yerleşiklerin görünen adı `name` ile dile göre gelir
    mode: str  # "white" | "colour"
    bright: int  # yüzde 1-100
    temp: int = 0  # beyaz mod: 0 sıcak … 100 soğuk
    hue: int = 0  # renk modu: 0-360
    sat: int = 0  # renk modu: 0-1000
    label: str = ""  # kullanıcının verdiği ad (yerleşiklerde boş)

    @property
    def builtin(self) -> bool:
        return not self.key.startswith(USER_PREFIX)

    @property
    def name(self) -> str:
        return self.label or tr(f"preset.{self.key}")

    def swatch(self) -> RGB:
        if self.mode == "white":
            return white_rgb(self.temp)
        return hs_rgb(self.hue, self.sat)


PRESETS: tuple[Preset, ...] = (
    Preset("reading", "white", 85, temp=45),
    Preset("focus", "white", 100, temp=100),
    Preset("night", "white", 8, temp=0),
    Preset("movie", "colour", 20, hue=28, sat=900),
    Preset("romantic", "colour", 25, hue=338, sat=850),
    Preset("ocean", "colour", 45, hue=200, sat=900),
)


class PresetError(ValueError):
    """Hazır ayar işlemi reddedildi; `code` arayüzde çevrilmiş metne dönüşür (`presets.error_<code>`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def clean_name(name: str) -> str:
    return " ".join(str(name).split())


def _clamp(value: object, low: int, high: int, default: int) -> int:
    try:
        number = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(high, number))


def normalise_values(mode: object, bright: object, temp: object, hue: object, sat: object) -> tuple[str, int, int, int, int]:
    """Sınır dışı değerleri sınırlar; mod geçersizse PresetError."""
    if mode not in ("white", "colour"):
        raise PresetError("values")
    return (
        str(mode),
        _clamp(bright, 1, 100, 50),
        _clamp(temp, 0, 100, 0),
        _clamp(hue, 0, 360, 0),
        _clamp(sat, 0, 1000, 0),
    )


def default_path() -> Path:
    import devices

    return devices.user_data_dir() / "presets.json"


class PresetStore:
    """Yerleşik + kullanıcı ayarları. `path=None` ise diske yazmaz (testler, örnek veriler).

    Yerleşik ayarlar silinemez ve değiştirilemez; yalnızca gizlenebilir. Dosyada gizli bilgi yoktur.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self._user: list[Preset] = []
        self._hidden: set[str] = set()
        self.recovered_from: Path | None = None  # dosya bozuksa: yedeğin yolu
        self.problem = False  # dosya bozuktu ya da bazı kayıtlar atlandı

    # -- okuma / yazma --------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> PresetStore:
        store = cls(path if path is not None else default_path())
        assert store.path is not None
        data, backup, corrupt = storage.load_json(store.path)
        if corrupt:
            store.problem, store.recovered_from = True, backup
            return store
        if data is None:
            return store
        if not isinstance(data, dict):
            store.problem, store.recovered_from = True, storage.backup_file(store.path)
            return store
        builtin_keys = {p.key for p in PRESETS}
        hidden = data.get("hidden")
        if isinstance(hidden, list):
            store._hidden = {k for k in hidden if isinstance(k, str) and k in builtin_keys}
        items = data.get("presets")
        skipped = 0
        for item in items if isinstance(items, list) else []:
            preset = store._parse_item(item)
            if preset is None:
                skipped += 1
            else:
                store._user.append(preset)
        if items is not None and not isinstance(items, list):
            skipped += 1
        if skipped:
            store.problem, store.recovered_from = True, storage.backup_file(store.path)
        return store

    def _parse_item(self, item: object) -> Preset | None:
        if not isinstance(item, dict):
            return None
        key, name = item.get("id"), clean_name(item.get("name", ""))
        if not isinstance(key, str) or not key.startswith(USER_PREFIX) or any(p.key == key for p in self._user):
            return None
        # Yerleşik adlar dile göre değişir: yüklerken yalnızca kullanıcı ayarları arasındaki yinelemeye bakılır.
        if not name or len(name) > MAX_NAME or any(p.name.casefold() == name.casefold() for p in self._user):
            return None
        try:
            mode, bright, temp, hue, sat = normalise_values(
                item.get("mode"), item.get("bright"), item.get("temp"), item.get("hue"), item.get("sat")
            )
        except PresetError:
            return None
        return Preset(key, mode, bright, temp, hue, sat, label=name)

    def save(self) -> None:
        if self.path is None:
            return
        payload = {
            "version": STORE_VERSION,
            "hidden": sorted(self._hidden),
            "presets": [
                {"id": p.key, "name": p.label, "mode": p.mode, "bright": p.bright, "temp": p.temp, "hue": p.hue, "sat": p.sat}
                for p in self._user
            ],
        }
        storage.write_json_atomic(self.path, payload)

    # -- sorgu ----------------------------------------------------------------

    def all(self) -> list[Preset]:
        return [*PRESETS, *self._user]

    def visible(self) -> list[Preset]:
        return [p for p in self.all() if p.key not in self._hidden]

    def user_presets(self) -> list[Preset]:
        return list(self._user)

    def is_hidden(self, key: str) -> bool:
        return key in self._hidden

    def get(self, key: str) -> Preset | None:
        return next((p for p in self.all() if p.key == key), None)

    def find(self, text: str) -> Preset | None:
        """Ada (büyük/küçük harf fark etmez) ya da kimliğe göre bulur; gizli yerleşik ayarlar da bulunur."""
        wanted = clean_name(text).casefold()
        if not wanted:
            return None
        for preset in (*self._user, *PRESETS):
            if preset.name.casefold() == wanted or preset.key.casefold() == wanted:
                return preset
        return None

    # -- değişiklik -----------------------------------------------------------

    def _name_taken(self, name: str, ignore: str = "") -> bool:
        wanted = name.casefold()
        return any(p.name.casefold() == wanted for p in self.all() if p.key != ignore)

    def _check_name(self, name: str, ignore: str = "") -> str:
        name = clean_name(name)
        if not name:
            raise PresetError("empty")
        if len(name) > MAX_NAME:
            raise PresetError("too_long")
        if self._name_taken(name, ignore):
            raise PresetError("duplicate")
        return name

    def add(self, name: str, mode: str, bright: int, temp: int = 0, hue: int = 0, sat: int = 0) -> Preset:
        name = self._check_name(name)
        if len(self._user) >= MAX_USER_PRESETS:
            raise PresetError("limit")
        values = normalise_values(mode, bright, temp, hue, sat)
        key = USER_PREFIX + secrets.token_hex(4)
        while self.get(key) is not None:
            key = USER_PREFIX + secrets.token_hex(4)
        preset = Preset(key, *values, label=name)
        self._user.append(preset)
        self.save()
        return preset

    def update(self, key: str, name: str, mode: str, bright: int, temp: int = 0, hue: int = 0, sat: int = 0) -> Preset:
        index = next((i for i, p in enumerate(self._user) if p.key == key), -1)
        if index < 0:
            raise PresetError("builtin" if any(p.key == key for p in PRESETS) else "unknown")
        name = self._check_name(name, ignore=key)
        values = normalise_values(mode, bright, temp, hue, sat)
        preset = Preset(key, *values, label=name)
        self._user[index] = preset
        self.save()
        return preset

    def delete(self, key: str) -> None:
        if any(p.key == key for p in PRESETS):
            raise PresetError("builtin")
        before = len(self._user)
        self._user = [p for p in self._user if p.key != key]
        if len(self._user) == before:
            raise PresetError("unknown")
        self.save()

    def set_hidden(self, key: str, hidden: bool) -> None:
        """Yalnızca yerleşik ayarlar gizlenir; kullanıcı ayarları silinir."""
        if not any(p.key == key for p in PRESETS):
            raise PresetError("unknown")
        if hidden:
            self._hidden.add(key)
        else:
            self._hidden.discard(key)
        self.save()
