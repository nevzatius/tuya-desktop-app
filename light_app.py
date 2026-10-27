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


def main() -> int:
    from PySide6.QtCore import QLockFile, QSettings, Qt
    from PySide6.QtWidgets import QApplication, QMessageBox

    import devices as dv
    import energy
    import i18n
    import light_core as lc
    from i18n import tr
    from version import APP_NAME
    from ui.bridge import LightBridge
    from ui.controller import AppController
    from ui.setup_dialog import SetupDialog
    from ui.icons import app_icon
    from ui.main_window import MainWindow
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

    try:
        store = dv.DeviceStore.load(legacy_config=lc.CONFIG_PATH)
    except dv.StoreError as exc:
        QMessageBox.critical(None, APP_NAME, tr("app.store_error", error=exc))
        return 1

    if store.current() is None:  # ilk açılış: sihirbaz
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
    window = MainWindow(cfg, bridge, energy_log=energy_log)
    tracker = energy.UsageTracker(energy_log) if energy_log is not None else None
    AppController(store, bridge, window, tracker=tracker)
    if not start_hidden(sys.argv, window.has_tray):
        window.show()
    bridge.start()
    code = app.exec()
    bridge.shutdown()
    if energy_log is not None:
        energy_log.close()  # açık aralıkları kapatır
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
