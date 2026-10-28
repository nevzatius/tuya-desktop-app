"""Masaüstü uygulaması (PySide6) giriş noktası.

    python light_app.py
"""

from __future__ import annotations

import os
import sys
import tempfile


def start_hidden(argv: list[str], has_tray: bool) -> bool:
    """"Windows ile başlat" ile açılınca (--minimized) pencere yerine yalnızca tepsi simgesi görünsün."""
    return "--minimized" in argv and has_tray


_STD_STREAMS = (("stdout", -11), ("stderr", -12))  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
_BAD_HANDLES = (None, 0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)  # NULL ve INVALID_HANDLE_VALUE


def _kernel32():
    import ctypes
    from ctypes import c_uint32, c_void_p

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.GetStdHandle.argtypes, k.GetStdHandle.restype = [c_uint32], c_void_p
    k.GetFileType.argtypes, k.GetFileType.restype = [c_void_p], c_uint32
    k.AttachConsole.argtypes, k.AttachConsole.restype = [c_uint32], c_uint32
    return k


def _open_console():
    return open("CONOUT$", "w", encoding="utf-8", buffering=1)  # noqa: SIM115


def attach_console(kernel32=None) -> None:
    """Konsolsuz (pencere) exe komut satırından çalıştırılınca mesajlar görünsün.

    Önce üst sürecin yönlendirdiği (boru, dosya: `> cikti.txt`, `2>&1`) standart tutamaçlar kullanılır; yönlendirme yoksa
    üst sürecin konsoluna bağlanılır (ATTACH_PARENT_PROCESS). Konsol da yoksa akışlar olduğu gibi kalır (sessiz geçilir).
    """
    if sys.platform != "win32" or not (getattr(sys, "frozen", False) or sys.stdout is None or sys.stderr is None):
        return
    try:
        import msvcrt

        k = kernel32 or _kernel32()
        owned: dict[object, object] = {}  # tutamaç -> akış (`2>&1`: iki akış aynı tutamacı paylaşır, bir kez açılır)
        console: object | None = None
        attached: bool | None = None
        streams: dict[str, object] = {}
        for name, std_id in _STD_STREAMS:
            handle = k.GetStdHandle(std_id)
            if handle not in _BAD_HANDLES and k.GetFileType(handle) != 0:  # 0 = FILE_TYPE_UNKNOWN
                if handle not in owned:
                    owned[handle] = open(msvcrt.open_osfhandle(handle, os.O_WRONLY), "w", encoding="utf-8", buffering=1)  # noqa: SIM115
                streams[name] = owned[handle]
                continue
            if attached is None:
                attached = bool(k.AttachConsole(0xFFFFFFFF))  # ATTACH_PARENT_PROCESS
            if attached:
                console = console or _open_console()
                streams[name] = console
        for name, stream in streams.items():
            setattr(sys, name, stream)
    except Exception:  # noqa: BLE001 - konsol yoksa sessizce devam
        pass


def devices_problem_text(store) -> str:
    """Işık listesi dosyası bozuksa kullanıcıya gösterilecek açıklama (boşsa sorun yok). Yedek adı verilir, yol değil."""
    if not store.problem:
        return ""
    from i18n import tr

    head = tr("app.devices_recovered" if store.current() is None else "app.devices_partial")
    backup = tr("app.devices_backup_failed") if store.recovered_from is None else tr("app.devices_backup_kept", backup=store.recovered_from.name)
    return f"{head}\n\n{backup}"


def run_quick(argv: list[str], channel: str | None = None) -> int | None:
    """`--scene "Film"` / `--power on|off`: komutu ÇALIŞAN uygulamaya iletir ve çıkış kodunu döndürür.

    Hızlı komut yoksa None (normal uygulama başlar). Tek-örnek kilidi alınmaz ve pencere açılmaz.
    """
    import quick_cli as qc

    error: qc.UsageError | None = None
    try:
        command = qc.parse(argv)
    except qc.UsageError as exc:
        command, error = None, exc
    if command is None and error is None:
        return None

    from PySide6.QtCore import QCoreApplication, QSettings

    import i18n
    from i18n import tr
    from version import APP_NAME

    app = QCoreApplication.instance() or QCoreApplication(argv)
    app.setOrganizationName("TuyaLight")
    app.setApplicationName("RoomLight")
    i18n.init(str(QSettings().value(i18n.SETTINGS_KEY, i18n.AUTO)))
    attach_console()
    for stream in (sys.stdout, sys.stderr):  # eski konsol kod sayfaları metni yazamasa da komut çökmesin
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if error is not None:
        print(tr(f"cli.usage_{error.code}"), file=sys.stderr)
        return qc.EXIT_USAGE
    if command == qc.HELP:
        print(tr("cli.help", program=os.path.basename(argv[0]) or APP_NAME))
        return qc.EXIT_OK
    from ui import ipc

    reply = ipc.send_command(command, channel)
    print(reply.text, file=sys.stdout if reply.exit_code == qc.EXIT_OK else sys.stderr)
    return reply.exit_code


def main() -> int:
    quick = run_quick(sys.argv)
    if quick is not None:
        return quick

    import applog
    import diagnostics

    store = None  # ışık deposu (aşağıda yüklenir); günlük, depodaki gizli değerleri her satırda maskeler
    applog.setup(secrets=lambda: diagnostics.known_secrets(store.devices()) if store is not None else [])
    applog.install_excepthooks()

    from PySide6.QtCore import QLockFile, QSettings, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    import automation as au
    import devices as dv
    import energy
    import i18n
    import light_core as lc
    from i18n import tr
    from version import APP_NAME
    from ui.automation_host import AutomationHost, LightBackend
    from ui.bridge import LightBridge
    from ui.hotkeys import HotkeyManager
    from ui import ipc
    from ui.controller import AppController
    from ui.setup_dialog import SetupDialog
    from ui.icons import app_icon
    from ui.main_window import MainWindow
    from ui.presets import PresetStore
    from ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setOrganizationName("TuyaLight")
    app.setApplicationName("RoomLight")
    i18n.init(str(QSettings().value(i18n.SETTINGS_KEY, i18n.AUTO)))  # dil: kayıtlı tercih ya da sistem dili
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # kapatınca tepside kalır
    apply_theme(app)

    # BLE'de ışığa aynı anda tek bağlantı olur: ikinci kopya açılmasın.
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "tuya_room_light.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        QMessageBox.information(None, APP_NAME, tr("app.already_running"))
        return 0

    dv.migrate_legacy_data()  # eski veri klasöründeki anahtarlar ve enerji kaydı yeni klasöre taşınır

    store = dv.DeviceStore.load(legacy_config=lc.CONFIG_PATH)  # bozuksa yedeği alınır; açılış çökmez
    problem_text = devices_problem_text(store)
    if problem_text:
        QMessageBox.warning(None, APP_NAME, problem_text)

    if store.current() is None:  # ilk açılış (ya da dosya bozuktu): sihirbaz
        dialog = SetupDialog()
        if dialog.exec() != dialog.DialogCode.Accepted or not dialog.added_devices():
            return 0
        for added in dialog.added_devices():
            store.add(added)
        store.save()

    cfg = store.current()
    try:
        energy_log = energy.EnergyLog()
    except Exception:  # noqa: BLE001 - disk/izin sorunu enerji kaydını engellemesin
        energy_log = None
    bridge = LightBridge(cfg)
    presets = PresetStore.load()  # bozuksa yedeği alınır, yerleşik ayarlarla devam edilir
    rules = au.RuleStore.load()  # bozuksa yedeği alınır, boş başlanır
    host = AutomationHost(
        rules,
        au.EngineState.load(),
        LightBackend(store, bridge),
        resolve_preset=presets.get,
        notify=lambda text: window.notice(text),  # pencere hemen aşağıda oluşur
    )
    hotkeys = HotkeyManager()  # yalnızca Windows'ta etkin
    window = MainWindow(cfg, bridge, energy_log=energy_log, preset_store=presets, automation_host=host, hotkey_manager=hotkeys)
    tracker = energy.UsageTracker(energy_log) if energy_log is not None else None
    AppController(store, bridge, window, tracker=tracker)
    hotkeys.triggered.connect(window.apply_preset_key)
    command_server = ipc.CommandServer(
        ipc.make_handler(
            presets.find,
            lambda: [p.name for p in presets.all()],
            window.apply_preset_key,
            bridge.set_power,
            lambda: store.current() is not None,
        )
    )
    command_server.start()  # tek-örnek kilidini aldıktan sonra: komut satırı bu kanaldan çalışan uygulamaya ulaşır
    if not start_hidden(sys.argv, window.has_tray):
        window.show()
    if presets.problem:
        window.notice(tr("presets.recovered"))
    if rules.problem:
        window.notice(tr("automation.recovered"))
    failed = hotkeys.apply(presets.hotkeys())  # başka uygulamanın aldığı kısayollar kaydedilemez
    if failed:
        window.notice(tr("presets.hotkey_startup_failed", names=", ".join(p.name for k in failed if (p := presets.get(k)) is not None)))
    bridge.start()
    host.start()
    code = app.exec()
    command_server.close()
    hotkeys.shutdown()
    host.shutdown()
    bridge.shutdown()
    if energy_log is not None:
        energy_log.close()  # açık aralıkları kapatır
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
