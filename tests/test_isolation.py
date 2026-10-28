"""Test yalıtımı (conftest `_isolated_world`): testler gerçek cihaza, çalışan uygulamaya ve kullanıcı verisine dokunmaz."""

from __future__ import annotations

import getpass
import os
import sys
import tempfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

import devices as dv
import light_core as lc
import quick_cli as qc
from conftest import REAL_CHANNEL, FakeWin32Hotkeys, IsolationError
from ui import hotkeys, ipc


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


POWER_ON = qc.QuickCommand({"cmd": "power", "on": True})


def test_the_real_channel_name_is_the_one_the_running_app_uses():
    assert REAL_CHANNEL.startswith("TuyaDesktopApp-") and not REAL_CHANNEL.startswith("TuyaDesktopAppTest")


def test_real_channel_name_is_named_after_the_user():
    assert REAL_CHANNEL == f"TuyaDesktopApp-{getpass.getuser().replace(' ', '_')}"
    assert ipc.server_name("ali veli").endswith("-ali_veli") and ipc.server_name("a/b\\c").endswith("-a_b_c")


def test_default_channel_name_is_unique_and_never_the_real_one():
    assert ipc.server_name() != REAL_CHANNEL
    assert ipc.server_name().startswith("TuyaDesktopAppTest-")


def test_a_command_without_explicit_channel_does_not_reach_the_running_app(qapp):
    """Çalışan uygulama varmış gibi: varsayılan adla gönderilen komut gerçek kanala gitmez, "çalışmıyor" döner."""
    reply = ipc.send_command(POWER_ON, timeout_ms=500)
    assert reply.exit_code == qc.EXIT_NOT_RUNNING


def test_connecting_to_the_real_channel_is_refused_by_the_guard(qapp):
    with pytest.raises(IsolationError):
        ipc.send_command(POWER_ON, REAL_CHANNEL, 500)
    with pytest.raises(IsolationError):
        QLocalSocket().connectToServer(REAL_CHANNEL)


def test_listening_on_the_real_channel_is_refused_by_the_guard(qapp):
    with pytest.raises(IsolationError):
        QLocalServer().listen(REAL_CHANNEL)
    with pytest.raises(IsolationError):
        ipc.CommandServer(lambda command: {"ok": True}, REAL_CHANNEL).start()


def test_data_folders_point_at_a_temporary_directory(_isolated_world):
    world = _isolated_world
    base = {"win32": world / "appdata", "darwin": world / "home" / "Library" / "Application Support"}.get(sys.platform, world / "xdg")
    assert dv.user_data_dir() == base / dv.APP_FOLDER
    assert Path.home() == world / "home"
    assert Path(tempfile.gettempdir()) == world / "temp"
    for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "HOME", "USERPROFILE", "TEMP", "TMP"):
        assert Path(os.environ[name]).is_relative_to(world), name


def test_the_legacy_config_json_is_not_the_real_one(_isolated_world):
    assert lc.CONFIG_PATH == _isolated_world / "config.json"
    assert not lc.CONFIG_PATH.exists()
    with pytest.raises(lc.ConfigError):  # varsayılan yol: gerçek (içinde anahtar olan) config.json okunmaz
        lc.Config.load()
    lc.Config("d", "k", "u").save()  # varsayılan yol: gerçek dosyanın üzerine yazılmaz
    assert (_isolated_world / "config.json").exists()


def test_qsettings_writes_to_a_temporary_ini_not_the_registry(_isolated_world):
    import ui.main_window as main_window

    for settings in (main_window.QSettings("TuyaLight", "RoomLight"), QSettings()):  # MainWindow'un varsayılanı, light_app'in
        assert settings.format() == QSettings.Format.IniFormat  # yazmadan önce denetlenir: kayıt defterine hiçbir şey gitmez
        assert Path(settings.fileName()).is_relative_to(_isolated_world)


def test_no_other_module_builds_registry_backed_settings():
    """`QSettings("org", "app")` yalnızca main_window'da kurulur (testte .ini'ye çevrilen yer); yenisi eklenirse burası uyarır."""
    import re

    found = {
        path.name
        for path in [*Path(dv.__file__).parent.glob("*.py"), *(Path(dv.__file__).parent / "ui").glob("*.py")]
        if re.search(r'QSettings\(\s*"', path.read_text(encoding="utf-8"))
    }
    assert found == {"main_window.py"}


def test_bluetooth_is_blocked():
    import asyncio

    from bleak import BleakClient, BleakScanner

    async def scan():
        async with BleakScanner():
            pass

    with pytest.raises(IsolationError):
        asyncio.run(scan())
    with pytest.raises(IsolationError):
        BleakClient("AA:BB:CC:DD:EE:FF")
    with pytest.raises(IsolationError):
        asyncio.run(BleakScanner.discover(timeout=0.1))


def test_hotkeys_use_the_fake_backend_and_emulate_conflicts(qapp):
    manager = hotkeys.HotkeyManager(available=True)
    assert manager.apply({"movie": "Ctrl+Alt+Shift+F12"}) == {}
    assert isinstance(manager._backend, FakeWin32Hotkeys)
    assert hotkeys.WindowsBackend is FakeWin32Hotkeys
    other = hotkeys.HotkeyManager(available=True)
    assert other.apply({"movie": "Ctrl+Alt+Shift+F12"}) == {"movie": "conflict"}
    manager.shutdown()
    other.shutdown()
    assert FakeWin32Hotkeys.registry == {}


def test_the_guard_is_documented_for_contributors_and_for_claude():
    root = Path(__file__).resolve().parents[1]
    contributing = (root / "CONTRIBUTING.md").read_text(encoding="utf-8")
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    assert "never touch a real light or a running copy of the app" in contributing and "tests/conftest.py" in contributing
    assert "_isolated_world" in claude and "gerçek cihaza ve çalışan uygulamaya dokunmamalı" in claude
