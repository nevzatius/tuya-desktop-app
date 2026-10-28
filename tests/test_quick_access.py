"""Hızlı erişim: komut satırı + yerel kanal, tepsi menüsü, genel kısayollar."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QLockFile, QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import automation as au  # noqa: E402
import i18n  # noqa: E402
import light_app  # noqa: E402
import light_core as lc  # noqa: E402
import quick_cli as qc  # noqa: E402
import shortcuts  # noqa: E402
from automation_helpers import FakeBackend, make_rule  # noqa: E402
from qt_helpers import FakeBridge  # noqa: E402
from ui import ipc  # noqa: E402
from ui.automation_host import AutomationHost  # noqa: E402
from ui.icons import app_icon  # noqa: E402
from ui.hotkeys import ERROR_HOTKEY_ALREADY_REGISTERED, WM_HOTKEY, HotkeyManager, _Filter  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.presets import PRESETS, PresetError, PresetStore  # noqa: E402
from ui.presets_view import HotkeyDialog, ManagePresetsDialog  # noqa: E402
from ui.theme import apply_theme  # noqa: E402
from ui.tray import TrayController  # noqa: E402

CFG = lc.Config(device_id="bf0123456789abcdefghij", local_key="TestKey#0123456!", uuid="0123456789abcdef", name="Test ışığı")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


# =============================== komut satırı ayrıştırma ===============================


@pytest.mark.parametrize(
    ("argv", "payload"),
    [
        (["app", "--scene", "Film"], {"cmd": "scene", "name": "Film"}),
        (["app", "--scene=Film gecesi"], {"cmd": "scene", "name": "Film gecesi"}),
        (["app", "--minimized", "--scene", "  Okuma "], {"cmd": "scene", "name": "Okuma"}),
        (["app", "--power", "on"], {"cmd": "power", "on": True}),
        (["app", "--power=OFF"], {"cmd": "power", "on": False}),
    ],
)
def test_parse_quick_commands(argv, payload):
    command = qc.parse(argv)
    assert isinstance(command, qc.QuickCommand) and command.payload == payload


def test_no_quick_command_means_the_normal_app_starts():
    assert qc.parse(["app"]) is None and qc.parse(["app", "--minimized"]) is None
    assert qc.parse(["app", "-h"]) == qc.HELP and qc.parse(["app", "--help"]) == qc.HELP


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["app", "--scene"], "missing"),
        (["app", "--power"], "missing"),
        (["app", "--power", "maybe"], "power_value"),
        (["app", "--scene", "  "], "empty_scene"),
        (["app", "--scene", "Film", "--power", "on"], "both"),
    ],
)
def test_parse_usage_errors(argv, code):
    with pytest.raises(qc.UsageError) as err:
        qc.parse(argv)
    assert err.value.code == code


# =============================== yerel kanal ===============================


class Recorder:
    def __init__(self, store: PresetStore, light: bool = True):
        self.applied: list[str] = []
        self.power: list[bool] = []
        self.handler = ipc.make_handler(
            store.find,
            lambda: [p.name for p in store.all()],
            lambda key: self.applied.append(key),
            lambda on: self.power.append(on),
            lambda: light,
        )


@pytest.fixture()
def channel(qapp, tmp_path):
    """Çalışan "uygulama": gerçek QLocalServer; istemci ayrı iş parçacığında (engelleyici çağrılar için)."""
    store = PresetStore(tmp_path / "presets.json")
    store.add("Çalışma masası", "white", 70, temp=60)
    recorder = Recorder(store)
    name = f"TuyaDesktopAppTest-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    server = ipc.CommandServer(recorder.handler, name)
    assert server.start()

    def send(command, timeout_ms=3000):
        result: dict = {}
        thread = threading.Thread(target=lambda: result.update(reply=ipc.send_command(command, name, timeout_ms)))
        thread.start()
        while thread.is_alive():
            QApplication.processEvents()
            thread.join(0.01)
        return result["reply"]

    yield recorder, send, name, server, store
    server.close()


def test_scene_command_applies_the_preset_by_name_case_insensitively(channel):
    recorder, send, *_ = channel
    reply = send(qc.QuickCommand({"cmd": "scene", "name": "film"}))
    assert (reply.exit_code, reply.text) == (qc.EXIT_OK, "“Film” ayarı uygulamaya iletildi.")
    assert recorder.applied == ["movie"]


def test_user_presets_work_too_and_unknown_names_are_rejected_with_the_available_list(channel):
    recorder, send, *_ = channel
    assert send(qc.QuickCommand({"cmd": "scene", "name": "Çalışma masası"})).exit_code == qc.EXIT_OK
    assert recorder.applied[-1].startswith("u-")
    reply = send(qc.QuickCommand({"cmd": "scene", "name": "Yok böyle"}))
    assert reply.exit_code == qc.EXIT_REJECTED and "Yok böyle" in reply.text and "Film" in reply.text and "Çalışma masası" in reply.text
    assert len(recorder.applied) == 1


def test_power_commands(channel):
    recorder, send, *_ = channel
    assert send(qc.QuickCommand({"cmd": "power", "on": True})).exit_code == qc.EXIT_OK
    assert send(qc.QuickCommand({"cmd": "power", "on": False})).text == "Işığı kapatma komutu uygulamaya iletildi."
    assert recorder.power == [True, False]


def test_reply_is_localized(channel):
    recorder, send, *_ = channel
    i18n.set_language("en")
    assert send(qc.QuickCommand({"cmd": "scene", "name": "Movie"})).text == "The preset “Movie” was sent to the app."


def test_app_without_a_light_rejects_commands(qapp, tmp_path):
    store = PresetStore(tmp_path / "p.json")
    recorder = Recorder(store, light=False)
    assert recorder.handler({"cmd": "power", "on": True}) == {"ok": False, "code": "no_light"}
    assert recorder.power == [] and recorder.applied == []


@pytest.mark.parametrize(
    "command",
    [{}, {"cmd": "format-disk"}, {"cmd": "scene"}, {"cmd": "scene", "name": 5}, {"cmd": "scene", "name": " "}, {"cmd": "power"}, {"cmd": "power", "on": "yes"}],
)
def test_malformed_commands_are_rejected_without_side_effects(qapp, tmp_path, command):
    recorder = Recorder(PresetStore(tmp_path / "p.json"))
    assert recorder.handler(command)["ok"] is False
    assert recorder.applied == [] and recorder.power == []


def raw_exchange(name, payload: bytes):
    """Ham bayt gönderir, yanıtı döndürür (istemci kitaplığını atlar). Olay döngüsüyle, ayrı iş parçacığında."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtNetwork import QLocalSocket

    box: dict = {"data": b""}

    def run():
        loop, socket, timer = QEventLoop(), QLocalSocket(), QTimer()
        timer.setSingleShot(True)

        def ready():
            box["data"] += bytes(socket.readAll())
            if b"\n" in box["data"]:
                loop.quit()

        socket.connected.connect(lambda: (socket.write(payload), socket.flush()))
        socket.readyRead.connect(ready)
        socket.disconnected.connect(loop.quit)
        socket.errorOccurred.connect(lambda *_: loop.quit())
        timer.timeout.connect(loop.quit)
        socket.connectToServer(name)
        timer.start(3000)
        loop.exec()
        socket.abort()

    thread = threading.Thread(target=run)
    thread.start()
    while thread.is_alive():
        QApplication.processEvents()
        thread.join(0.01)
    return box["data"]


def test_garbage_oversized_and_non_object_messages_get_a_rejection_and_do_not_break_the_server(channel):
    recorder, send, name, server, store = channel
    assert b'"bad_command"' in raw_exchange(name, b"not json at all\n")
    assert b'"bad_command"' in raw_exchange(name, b"[1,2,3]\n")
    assert b'"bad_command"' in raw_exchange(name, b"\xff\xfe\xfd\n")
    assert b'"bad_command"' in raw_exchange(name, b"x" * (ipc.MAX_MESSAGE + 500))
    assert recorder.applied == [] and recorder.power == []
    assert send(qc.QuickCommand({"cmd": "power", "on": True})).exit_code == qc.EXIT_OK  # hâlâ çalışıyor


def test_handler_crash_is_contained(qapp):
    def boom(command):
        raise RuntimeError("işleyici çöktü")

    name = f"TuyaDesktopAppTest-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    server = ipc.CommandServer(boom, name)
    assert server.start()
    try:
        assert b'"error"' in raw_exchange(name, b'{"cmd":"power","on":true}\n')
    finally:
        server.close()


def test_channel_is_limited_to_the_local_user_and_named_after_them(channel):
    recorder, send, name, server, store = channel
    assert server.user_only()
    prefix = ipc.SERVER_PREFIX  # testte benzersiz önek (conftest); gerçek önek "TuyaDesktopApp"
    assert ipc.server_name("ali veli") == f"{prefix}-ali_veli" and ipc.server_name("a/b\\c") == f"{prefix}-a_b_c"


def test_not_running_gives_a_clear_message_and_exit_code(qapp):
    reply = ipc.send_command(qc.QuickCommand({"cmd": "power", "on": True}), f"TuyaDesktopAppTest-yok-{uuid.uuid4().hex}", 500)
    assert reply.exit_code == qc.EXIT_NOT_RUNNING == 2 and "çalışmıyor" in reply.text


def test_silent_server_gives_no_reply_exit_code(qapp):
    """Bağlanır ama yanıt vermeyen sunucu: istemci sonsuza kadar beklemez."""
    from PySide6.QtNetwork import QLocalServer

    name = f"TuyaDesktopAppTest-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    server = QLocalServer()
    assert server.listen(name)
    box: dict = {}
    thread = threading.Thread(target=lambda: box.update(reply=ipc.send_command(qc.QuickCommand({"cmd": "power", "on": True}), name, 300)))
    thread.start()
    while thread.is_alive():
        QApplication.processEvents()
        thread.join(0.01)
    server.close()
    assert box["reply"].exit_code == qc.EXIT_NO_REPLY


def test_run_quick_returns_exit_codes_and_prints(channel, capsys, monkeypatch):
    recorder, send, name, server, store = channel
    monkeypatch.setattr(i18n, "init", lambda *a, **k: "tr")  # kullanıcının kayıtlı dil tercihi teste karışmasın
    box: dict = {}

    def call(argv):
        thread = threading.Thread(target=lambda: box.update(code=light_app.run_quick(argv, name)))
        thread.start()
        while thread.is_alive():
            QApplication.processEvents()
            thread.join(0.01)
        return box["code"]

    assert light_app.run_quick(["app"]) is None  # hızlı komut yok: normal uygulama
    assert call(["app", "--scene", "Film"]) == 0
    assert "iletildi" in capsys.readouterr().out
    assert call(["app", "--scene", "Olmayan"]) == 1
    assert "Olmayan" in capsys.readouterr().err
    assert light_app.run_quick(["app", "--power", "x"], name) == 64
    assert "on ya da off" in capsys.readouterr().err
    assert light_app.run_quick(["app", "--help"], name) == 0 and "--scene" in capsys.readouterr().out


def test_quick_command_does_not_touch_the_single_instance_lock(channel, tmp_path):
    """Komut satırı kilidi almaz: uygulama (kilidin sahibi) çalışırken komut yine de ulaşır."""
    recorder, send, name, server, store = channel
    lock = QLockFile(str(tmp_path / "tuya_room_light.lock"))
    assert lock.tryLock(200)
    try:
        assert send(qc.QuickCommand({"cmd": "power", "on": True})).exit_code == 0
        assert lock.isLocked()  # kilit hâlâ uygulamanın elinde
    finally:
        lock.unlock()


def _run_quick_process(args, channel, **kw):
    """Gerçek süreç, benzersiz (kimsenin dinlemediği) bir kanalla: çalışan gerçek uygulamaya komut gitmesin."""
    code = f"import sys; import light_app; sys.exit(light_app.run_quick(['app', *{args!r}], {channel!r}))"
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, timeout=60, env=env, encoding="utf-8", **kw)


def test_real_process_without_the_app_exits_with_code_2_and_a_readable_message():
    """Gerçek süreç: uygulama çalışmıyorken `--scene Film`."""
    done = _run_quick_process(["--scene", "Film"], f"no-app-{uuid.uuid4().hex}", capture_output=True, text=True)
    assert done.returncode == 2
    assert done.stdout == ""  # hata çıktısı hata akışına gider (betiklerde ayrıştırılabilsin)
    assert "çalışmıyor" in done.stderr or "not running" in done.stderr  # dil, kullanıcının kayıtlı tercihine göre


# --- konsolsuz (windowed) exe: akışlar None gelir; mesaj yine de görünmeli ---

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows konsol API'si")


class FakeKernel32:
    """GetStdHandle/GetFileType/AttachConsole: hangi standart tutamaçlar devralınmış ve konsol var mı."""

    def __init__(self, handles=None, console=True):
        self.handles, self.console, self.attach_calls = handles or {}, console, 0

    def GetStdHandle(self, std_id):  # noqa: N802
        return self.handles.get(std_id)

    def GetFileType(self, handle):  # noqa: N802
        return 3  # FILE_TYPE_PIPE

    def AttachConsole(self, pid):  # noqa: N802
        self.attach_calls += 1
        assert pid == 0xFFFFFFFF  # ATTACH_PARENT_PROCESS
        return 1 if self.console else 0


def no_streams(monkeypatch):
    """Windowed exe gibi: akışlar None. (Fikstür olmaz: pytest yakalaması çağrı aşamasında akışları yeniden kurar.)"""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(light_app, "_open_console", lambda: "CONSOLE")


@win_only
def test_attach_console_leaves_normal_streams_alone(monkeypatch):
    kernel = FakeKernel32()
    light_app.attach_console(kernel)  # pytest altında akışlar var ve exe donmuş değil
    assert kernel.attach_calls == 0


@win_only
def test_attach_console_attaches_to_the_parent_console_when_nothing_is_redirected(monkeypatch):
    no_streams(monkeypatch)
    kernel = FakeKernel32(console=True)
    light_app.attach_console(kernel)
    assert sys.stdout == "CONSOLE" and sys.stderr == "CONSOLE" and kernel.attach_calls == 1


@win_only
def test_attach_console_without_a_console_stays_silent(monkeypatch, no_app_channel):
    no_streams(monkeypatch)
    kernel = FakeKernel32(console=False)
    light_app.attach_console(kernel)
    assert sys.stdout is None and sys.stderr is None
    assert light_app.run_quick(["app", "--power", "x"], no_app_channel) == qc.EXIT_USAGE  # çökmez; mesaj sessizce düşer


@win_only
def test_attach_console_survives_a_broken_console_api(monkeypatch):
    no_streams(monkeypatch)
    class Broken(FakeKernel32):
        def AttachConsole(self, pid):  # noqa: N802
            raise OSError("no console")

    light_app.attach_console(Broken())
    assert sys.stdout is None


@win_only
@pytest.mark.parametrize("merge", [False, True])
def test_real_process_with_no_console_streams_writes_to_redirected_handles(merge, no_app_channel):
    """Gerçek süreç, sys.stdout/stderr None (windowed exe gibi): yönlendirilen tutamaca yazar; `2>&1` de çalışır."""
    code = (
        "import sys; sys.stdout = sys.stderr = None; import light_app; "
        f"sys.exit(light_app.run_quick(['app', '--power', 'x'], {no_app_channel!r}))"
    )
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, timeout=60, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT if merge else subprocess.PIPE,
    )
    assert done.returncode == qc.EXIT_USAGE
    text = (done.stdout + (b"" if merge else done.stderr)).decode("utf-8")
    assert "on ya da off" in text or "on or off" in text
    if not merge:
        assert done.stdout == b""  # kullanım hatası hata akışında


# =============================== tepsi menüsü ===============================


def test_tray_menu_has_presets_submenu_and_pause_option(qapp):
    tray = TrayController(app_icon(), "Test", with_automation=True)
    store = PresetStore()
    store.add("Benim", "white", 50)
    store.set_hidden("night", True)
    tray.set_presets(store.visible())
    names = [a.text() for a in tray.presets_menu.actions()]
    assert names == ["Okuma", "Odak", "Film", "Romantik", "Okyanus", "Benim"]  # gizlenen yok, kullanıcı ayarı var
    picked, pauses = [], []
    tray.preset_requested.connect(picked.append)
    tray.automation_pause_requested.connect(pauses.append)
    next(a for a in tray.presets_menu.actions() if a.text() == "Film").trigger()
    assert picked == ["movie"]
    assert tray.pause_action.text() == "Otomasyonları duraklat"
    tray.pause_action.trigger()
    assert pauses == [True]
    tray.set_automation_paused(True)
    assert tray.pause_action.text() == "Otomasyonlara devam et"
    tray.pause_action.trigger()
    assert pauses == [True, False]


def test_tray_without_automation_has_no_pause_option(qapp):
    tray = TrayController(app_icon(), "Test")
    assert tray.pause_action is None
    tray.set_automation_paused(True)  # çökmemeli


@pytest.fixture()
def tray_window(qapp, tmp_path):
    bridge = FakeBridge()
    host = AutomationHost(au.RuleStore(tmp_path / "automations.json"), au.EngineState(tmp_path / "state.json"), FakeBackend(), submit=lambda c: c.close())
    store = PresetStore(tmp_path / "presets.json")
    win = MainWindow(CFG, bridge, settings=QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat), use_tray=False, preset_store=store, automation_host=host)
    win._setup_tray()
    yield win, bridge, host, store
    win.close()


def test_choosing_a_preset_from_the_tray_applies_it_like_a_chip_click(tray_window):
    win, bridge, host, store = tray_window
    tray = win._tray
    next(a for a in tray.presets_menu.actions() if a.text() == "Film").trigger()
    assert bridge.calls == [("scene", "Film")] and win.bright.value() == 20 and win.stack.currentIndex() == 1


def test_tray_presets_follow_changes_in_the_main_window(tray_window):
    win, bridge, host, store = tray_window
    store.add("Yeni ayar", "white", 40)
    win.presets_section.refresh()
    win.presets_section.changed.emit()
    assert "Yeni ayar" in [a.text() for a in win._tray.presets_menu.actions()]
    win.presets_section.toggle_hidden("ocean")
    assert "Okyanus" not in [a.text() for a in win._tray.presets_menu.actions()]


def pause_views(win):
    """Duraklatma durumunun üç görünümü: (sekmedeki uyarı bandı görünür mü, düğme yazısı, tepsi menüsü yazısı)."""
    page = win.automation_page
    return page.paused_banner.isVisible(), page.pause_button.text(), win._tray.pause_action.text()


RUNNING = (False, "Otomasyonları duraklat", "Otomasyonları duraklat")
PAUSED = (True, "Devam ettir", "Otomasyonlara devam et")


def test_pause_stays_in_sync_between_tab_tray_and_host(tray_window):
    win, bridge, host, store = tray_window
    win.show()
    win.tab_automation.click()
    assert pause_views(win) == RUNNING
    win._tray.pause_action.trigger()  # tepsiden duraklat
    assert host.scheduler.paused and pause_views(win) == PAUSED
    win.automation_page.pause_button.click()  # sekmeden devam ettir
    assert not host.scheduler.paused and pause_views(win) == RUNNING
    win.automation_page.pause_button.click()  # sekmeden duraklat
    assert host.scheduler.paused and pause_views(win) == PAUSED
    win._tray.pause_action.trigger()  # tepsiden devam ettir
    assert not host.scheduler.paused and pause_views(win) == RUNNING
    host.set_paused(True)  # doğrudan (ör. başka bir kod yolu)
    assert pause_views(win) == PAUSED


def test_app_opened_while_paused_shows_the_paused_state_everywhere(qapp, tmp_path):
    state = au.EngineState(tmp_path / "state.json")
    state.set_paused(True)  # önceki oturumda duraklatılmış ve kaydedilmiş
    host = AutomationHost(au.RuleStore(tmp_path / "automations.json"), au.EngineState.load(tmp_path / "state.json"), FakeBackend(), submit=lambda c: c.close())
    assert host.scheduler.paused
    win = MainWindow(CFG, FakeBridge(), settings=QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat), use_tray=False, preset_store=PresetStore(tmp_path / "presets.json"), automation_host=host)
    win._setup_tray()
    try:
        win.show()
        win.tab_automation.click()
        assert pause_views(win) == PAUSED
        win._tray.pause_action.trigger()  # tepsiden devam ettir: kalıcı durum da güncellenir
        assert pause_views(win) == RUNNING
        assert not au.EngineState.load(tmp_path / "state.json").paused
    finally:
        win.close()


def test_apply_preset_key_ignores_unknown_ids(tray_window):
    win, bridge, host, store = tray_window
    assert not win.apply_preset_key("u-yok") and bridge.calls == []
    assert win.apply_preset_key("reading") and bridge.calls == [("scene", "Okuma")]


# =============================== genel kısayollar ===============================


@pytest.mark.parametrize(
    ("text", "normal", "mods", "vk"),
    [
        ("ctrl+alt+f", "Ctrl+Alt+F", 0x2 | 0x1, ord("F")),
        ("Alt+1", "Alt+1", 0x1, ord("1")),
        ("Win+Shift+F12", "Shift+Win+F12", 0x4 | 0x8, 0x7B),
        ("Meta+Ctrl+F1", "Ctrl+Win+F1", 0x2 | 0x8, 0x70),
        ("  Ctrl + Alt + Z ", "Ctrl+Alt+Z", 0x3, ord("Z")),
    ],
)
def test_parse_combo(text, normal, mods, vk):
    assert shortcuts.parse_combo(text) == (mods, vk, normal)


@pytest.mark.parametrize(
    ("text", "code"),
    [("", "invalid"), ("F5", "needs_modifier"), ("Shift+A", "needs_modifier"), ("Ctrl", "needs_modifier"), ("Ctrl+Alt+Esc", "invalid"), ("Ctrl+F13", "invalid"), ("Ctrl+AB", "invalid"), ("Hyper+Ctrl+A", "invalid")],
)
def test_parse_combo_rejects(text, code):
    with pytest.raises(shortcuts.HotkeyError) as err:
        shortcuts.parse_combo(text)
    assert err.value.code == code


class FakeBackend_:
    def __init__(self, taken=()):
        self.taken = set(taken)
        self.registered: dict[int, tuple[int, int]] = {}
        self.log: list[tuple] = []

    def register(self, hotkey_id, mods, vk):
        self.log.append(("register", hotkey_id, mods, vk))
        if (mods, vk) in self.taken:
            return ERROR_HOTKEY_ALREADY_REGISTERED
        self.registered[hotkey_id] = (mods, vk)
        return 0

    def unregister(self, hotkey_id):
        self.log.append(("unregister", hotkey_id))
        self.registered.pop(hotkey_id, None)


def test_manager_registers_dispatches_and_reports_conflicts(qapp):
    backend = FakeBackend_(taken={(0x3, ord("B"))})
    manager = HotkeyManager(backend, available=True)
    fired = []
    manager.triggered.connect(fired.append)
    errors = manager.apply({"movie": "Ctrl+Alt+A", "reading": "Ctrl+Alt+B", "night": "Ctrl+Alt+Esc"})
    assert errors == {"reading": "conflict", "night": "invalid"}  # biri başkasında, biri geçersiz
    assert len(backend.registered) == 1
    (hotkey_id,) = backend.registered
    manager.handle(hotkey_id)
    manager.handle(0xDEAD)  # bilinmeyen kimlik yok sayılır
    assert fired == ["movie"]
    manager.shutdown()
    assert backend.registered == {}


def test_reapplying_releases_the_previous_registrations_first(qapp):
    backend = FakeBackend_()
    manager = HotkeyManager(backend, available=True)
    manager.apply({"movie": "Ctrl+Alt+A"})
    manager.apply({"movie": "Ctrl+Alt+B"})
    assert list(backend.registered.values()) == [(0x3, ord("B"))]
    assert [e[0] for e in backend.log] == ["register", "unregister", "register"]
    assert manager.apply({}) == {} and backend.registered == {}


def test_manager_is_inert_where_hotkeys_are_unavailable(qapp):
    backend = FakeBackend_()
    manager = HotkeyManager(backend, available=False)
    assert manager.apply({"movie": "Ctrl+Alt+A"}) == {} and backend.log == []
    assert HotkeyManager(available=sys.platform == "win32").available == (sys.platform == "win32")


@pytest.mark.skipif(sys.platform != "win32", reason="RegisterHotKey yalnızca Windows'ta")
def test_wm_hotkey_messages_reach_the_manager_through_the_native_event_filter(qapp):
    import ctypes.wintypes

    manager = HotkeyManager(FakeBackend_(), available=True)
    manager.apply({"movie": "Ctrl+Alt+A"})
    fired = []
    manager.triggered.connect(fired.append)
    msg = ctypes.wintypes.MSG()
    msg.message, msg.wParam = WM_HOTKEY, next(iter(manager._by_id))
    native = _Filter(manager.handle)
    assert native.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)) == (False, 0)
    msg.message = 0x0100  # WM_KEYDOWN: yok sayılır
    native.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg))
    native.nativeEventFilter(b"xcb_generic_event_t", 0)
    assert fired == ["movie"]
    manager.shutdown()


def test_hotkey_conflict_detection_uses_the_fake_win32_backend(qapp):
    """Çakışma yönetimi (conftest'teki sahte RegisterHotKey: gerçek Win32'ye ve kullanıcının kısayollarına dokunulmaz)."""
    first, second = HotkeyManager(available=True), HotkeyManager(available=True)
    combo = {"movie": "Ctrl+Alt+Shift+F12"}
    try:
        assert first.apply(combo) == {}
        assert second.apply(combo) == {"movie": "conflict"}  # çakışma: başka bir kayıt aynı tuşu alamaz
        first.shutdown()
        assert second.apply(combo) == {}  # serbest kalınca alınabilir
    finally:
        first.shutdown()
        second.shutdown()


# -- hazır ayar deposu: kısayol saklama ------------------------------------------------------------


def test_store_keeps_hotkeys_validates_and_persists(tmp_path):
    path = tmp_path / "presets.json"
    store = PresetStore(path)
    mine = store.add("Benim", "white", 50)
    assert store.set_hotkey("movie", "ctrl+alt+m") == "Ctrl+Alt+M"
    store.set_hotkey(mine.key, "Ctrl+Alt+B")
    with pytest.raises(PresetError) as err:
        store.set_hotkey("reading", "Alt+Ctrl+M")  # aynı kombinasyon başka ayarda
    assert err.value.code == "hotkey_duplicate"
    for bad, code in (("F5", "hotkey_needs_modifier"), ("Ctrl+Alt+Esc", "hotkey_invalid")):
        with pytest.raises(PresetError) as err:
            store.set_hotkey("reading", bad)
        assert err.value.code == code
    with pytest.raises(PresetError):
        store.set_hotkey("u-yok", "Ctrl+Alt+Q")
    loaded = PresetStore.load(path)
    assert loaded.hotkeys() == {"movie": "Ctrl+Alt+M", mine.key: "Ctrl+Alt+B"}
    loaded.set_hotkey("movie", "")  # kaldır
    assert PresetStore.load(path).hotkey_of("movie") == ""
    loaded.delete(mine.key)  # ayarla birlikte kısayolu da gider
    assert PresetStore.load(path).hotkeys() == {}


def test_invalid_hotkeys_in_the_file_are_dropped_with_a_backup(tmp_path):
    import json

    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"version": 1, "hotkeys": {"movie": "Ctrl+Alt+M", "reading": "Ctrl+Alt+M", "night": "F5", "u-yok": "Ctrl+Alt+Y", "ocean": 7}}), encoding="utf-8")
    store = PresetStore.load(path)
    assert store.hotkeys() == {"movie": "Ctrl+Alt+M"} and store.problem and store.recovered_from is not None


def test_old_files_without_hotkeys_still_load(tmp_path):
    import json

    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"version": 1, "hidden": [], "presets": []}), encoding="utf-8")
    store = PresetStore.load(path)
    assert store.hotkeys() == {} and not store.problem


# -- arayüz: kısayol atama ---------------------------------------------------------------------------


@pytest.fixture()
def section(qapp, tmp_path):
    from ui.presets_view import PresetsSection

    store = PresetStore(tmp_path / "presets.json")
    backend = FakeBackend_(taken={(0x3, ord("T"))})  # Ctrl+Alt+T başka uygulamada
    manager = HotkeyManager(backend, available=True)
    sec = PresetsSection(store, lambda: {"mode": "white", "bright": 50, "temp": 0, "hue": 0, "sat": 0}, hotkeys=manager)
    return sec, store, manager, backend


def test_setting_a_hotkey_registers_it_and_announces_the_change(section):
    sec, store, manager, backend = section
    changes = []
    sec.changed.connect(lambda: changes.append(1))
    assert sec.hotkeys_available()
    assert sec.set_hotkey("movie", "Ctrl+Alt+M") is None
    assert store.hotkey_of("movie") == "Ctrl+Alt+M" and (0x3, ord("M")) in backend.registered.values() and changes == [1]


def test_conflict_with_another_app_shows_an_error_and_keeps_the_old_shortcut(section):
    sec, store, manager, backend = section
    assert sec.set_hotkey("movie", "Ctrl+Alt+M") is None
    error = sec.set_hotkey("movie", "Ctrl+Alt+T")  # başka uygulama kullanıyor
    assert error == "Bu kombinasyonu başka bir uygulama kullanıyor. Başka bir kombinasyon deneyin."
    assert store.hotkey_of("movie") == "Ctrl+Alt+M" and list(backend.registered.values()) == [(0x3, ord("M"))]


def test_duplicate_and_invalid_combinations_give_clear_errors(section):
    sec, store, manager, backend = section
    sec.set_hotkey("movie", "Ctrl+Alt+M")
    assert "başka bir hazır ayarda" in sec.set_hotkey("reading", "Ctrl+Alt+M")
    assert "Ctrl, Alt ya da Win" in sec.set_hotkey("reading", "F5")
    assert "desteklenmiyor" in sec.set_hotkey("reading", "Ctrl+Alt+Esc")
    assert store.hotkey_of("reading") == ""


def test_hotkey_dialog_stays_open_on_error_and_closes_on_success(section):
    sec, store, manager, backend = section
    from PySide6.QtGui import QKeySequence

    dialog = HotkeyDialog("Film", "", lambda combo: sec.set_hotkey("movie", combo), None)
    dialog.edit.setKeySequence(QKeySequence("Ctrl+Alt+T"))
    dialog.save_button.click()
    assert not dialog.error.isHidden() and dialog.result() == 0 and "başka bir uygulama" in dialog.error.text()
    dialog.edit.setKeySequence(QKeySequence("Ctrl+Alt+M"))
    dialog.save_button.click()
    assert dialog.result() == 1 and store.hotkey_of("movie") == "Ctrl+Alt+M" and dialog.combo() == "Ctrl+Alt+M"


def test_manage_dialog_shows_the_shortcut_and_hides_the_feature_where_unavailable(section, qapp, tmp_path):
    sec, store, manager, backend = section
    sec.set_hotkey("movie", "Ctrl+Alt+M")
    dialog = ManagePresetsDialog(sec)
    assert not dialog.hotkey_button.isHidden()
    assert any("Ctrl+Alt+M" in dialog.list.item(i).text() for i in range(dialog.list.count()))
    from ui.presets_view import PresetsSection

    plain = PresetsSection(PresetStore(tmp_path / "x.json"), lambda: {}, hotkeys=HotkeyManager(available=False))
    assert not plain.hotkeys_available() and ManagePresetsDialog(plain).hotkey_button.isHidden()
    none = PresetsSection(PresetStore(tmp_path / "y.json"), lambda: {})
    assert not none.hotkeys_available() and not none.edit_hotkey("movie")


def test_every_builtin_can_get_a_shortcut(section):
    sec, store, manager, backend = section
    for index, preset in enumerate(PRESETS):
        assert sec.set_hotkey(preset.key, f"Ctrl+Alt+{index + 1}") is None
    assert len(backend.registered) == len(PRESETS)
