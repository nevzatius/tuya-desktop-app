"""Ortak test ayarları.

* Her test Türkçe başlar (mevcut testler Türkçe metinlere göre yazıldı).
* Testler gerçek cihaza, çalışan uygulamaya ve kullanıcının gerçek verisine DOKUNMAZ (autouse `_isolated_world`):
  veri klasörleri geçici dizine yönlenir, Bluetooth çağrısı hata verir, komut kanalı adı benzersizdir ve gerçek
  kanala bağlanma/dinleme engellenir, genel kısayol kaydı sahteye gider, QSettings .ini dosyasına yazar.
"""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import i18n  # noqa: E402
import light_core as lc  # noqa: E402
from ui import hotkeys, ipc  # noqa: E402

# Çalışan gerçek uygulamanın kanal adı: kanal öneki yamalanmadan ÖNCE hesaplanır.
REAL_CHANNEL = ipc.server_name()


class IsolationError(AssertionError):
    """Bir test gerçek cihaza, gerçek uygulamaya ya da gerçek kullanıcı verisine ulaşmaya çalıştı."""


class FakeWin32Hotkeys:
    """RegisterHotKey yerine bellekte kayıt: başka bir kayıt aynı kombinasyonu tutuyorsa 1409 (çakışma) döner."""

    registry: dict[tuple[int, int], int] = {}

    def __init__(self) -> None:
        self._mine: dict[int, tuple[int, int]] = {}

    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        combo = (mods, vk)
        if combo in FakeWin32Hotkeys.registry:
            return hotkeys.ERROR_HOTKEY_ALREADY_REGISTERED
        FakeWin32Hotkeys.registry[combo] = id(self)
        self._mine[hotkey_id] = combo
        return 0

    def unregister(self, hotkey_id: int) -> None:
        combo = self._mine.pop(hotkey_id, None)
        if combo is not None and FakeWin32Hotkeys.registry.get(combo) == id(self):
            del FakeWin32Hotkeys.registry[combo]


def _blocked(what: str):
    def refuse(*_args, **_kwargs):
        raise IsolationError(f"test gerçek Bluetooth'a dokundu: {what}")

    return refuse


@pytest.fixture(autouse=True)
def _turkish_ui():
    i18n.set_language("tr")
    i18n.set_currency(i18n.DEFAULT_CURRENCY)
    yield
    i18n.set_language("tr")
    i18n.set_currency(i18n.DEFAULT_CURRENCY)


@pytest.fixture(autouse=True)
def _isolated_world(monkeypatch, tmp_path_factory):
    home = tmp_path_factory.mktemp("world")  # test içindeki tmp_path'ten ayrı: oradaki dosya listelerini bozmaz
    for sub in ("appdata", "localappdata", "xdg", "home", "temp"):
        (home / sub).mkdir()
    monkeypatch.setenv("APPDATA", str(home / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "localappdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    monkeypatch.setenv("HOME", str(home / "home"))
    monkeypatch.setenv("USERPROFILE", str(home / "home"))
    monkeypatch.setenv("TEMP", str(home / "temp"))
    monkeypatch.setenv("TMP", str(home / "temp"))
    monkeypatch.setattr(tempfile, "tempdir", str(home / "temp"))  # tek-örnek kilidi gerçek %TEMP%'e yazmasın

    # Eski tek-ışıklı config.json (içinde yerel anahtar olabilir): gerçek dosya okunmaz/yazılmaz.
    legacy = home / "config.json"
    monkeypatch.setattr(lc, "CONFIG_PATH", legacy)
    monkeypatch.setattr(lc.Config.load.__func__, "__defaults__", (legacy,))
    monkeypatch.setattr(lc.Config.save, "__defaults__", (legacy,))

    # QSettings: Windows kayıt defteri yerine geçici .ini. `QSettings(org, app)` kurucusu varsayılan biçimi
    # kullanmaz (hep NativeFormat), bu yüzden onu kuran modüldeki ad .ini biçimli bir alt sınıfla değiştirilir.
    from PySide6.QtCore import QSettings

    import ui.main_window as main_window

    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(home / "settings"))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)

    class IniSettings(QSettings):
        def __init__(self, *args) -> None:
            if len(args) == 2 and all(isinstance(a, str) for a in args):
                super().__init__(QSettings.Format.IniFormat, QSettings.Scope.UserScope, *args)
            else:
                super().__init__(*args)

    monkeypatch.setattr(main_window, "QSettings", IniSettings)

    # Komut kanalı: benzersiz ad; gerçek kanala bağlanmak ya da onu dinlemek hata
    unique = f"TuyaDesktopAppTest-{uuid.uuid4().hex[:12]}"
    monkeypatch.setattr(ipc, "SERVER_PREFIX", unique)
    from PySide6.QtNetwork import QLocalServer, QLocalSocket

    def guard_name(args) -> None:
        name = args[0] if args else ""
        if isinstance(name, str) and name == REAL_CHANNEL:
            raise IsolationError("test çalışan gerçek uygulamanın komut kanalına dokundu")

    real_connect, real_listen = QLocalSocket.connectToServer, QLocalServer.listen

    def connect(self, *args, **kwargs):
        guard_name(args)
        return real_connect(self, *args, **kwargs)

    def listen(self, *args, **kwargs):
        guard_name(args)
        return real_listen(self, *args, **kwargs)

    monkeypatch.setattr(QLocalSocket, "connectToServer", connect)
    monkeypatch.setattr(QLocalServer, "listen", listen)

    # Bluetooth: tarama ve bağlanma hiçbir testte gerçek olamaz (testler kendi sahtesini koyar)
    import bleak
    import bleak_retry_connector

    monkeypatch.setattr(bleak.BleakScanner, "__init__", _blocked("BleakScanner"))
    monkeypatch.setattr(bleak.BleakScanner, "discover", _blocked("BleakScanner.discover"))
    monkeypatch.setattr(bleak.BleakClient, "__init__", _blocked("BleakClient"))
    monkeypatch.setattr(bleak_retry_connector, "establish_connection", _blocked("establish_connection"))
    import tuya_ble_sdk.client as sdk_client

    monkeypatch.setattr(sdk_client, "establish_connection", _blocked("establish_connection"))

    # Genel kısayol: gerçek RegisterHotKey yerine bellek içi sahte
    FakeWin32Hotkeys.registry = {}
    monkeypatch.setattr(hotkeys, "WindowsBackend", FakeWin32Hotkeys)

    yield home


@pytest.fixture()
def no_app_channel() -> str:
    """Hiçbir sunucunun dinlemediği, benzersiz kanal adı ("çalışan uygulama yok")."""
    return f"TuyaDesktopAppTest-yok-{uuid.uuid4().hex}"

