"""Sistem tepsisi simgesi ve menüsü."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from i18n import tr

from .presets import Preset
from .presets_view import dot_icon


class TrayController(QObject):
    power_requested = Signal(bool)
    show_requested = Signal()
    quit_requested = Signal()
    preset_requested = Signal(str)  # hazır ayar kimliği
    automation_pause_requested = Signal(bool)  # istenen durum: True = duraklat, False = devam ettir

    def __init__(self, icon: QIcon, title: str, parent: QObject | None = None, with_automation: bool = False) -> None:
        super().__init__(parent)
        self._title = title
        self._paused = False
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(title)
        menu = QMenu()
        menu.addAction(tr("tray.on")).triggered.connect(lambda: self.power_requested.emit(True))
        menu.addAction(tr("tray.off")).triggered.connect(lambda: self.power_requested.emit(False))
        menu.addSeparator()
        self.presets_menu = menu.addMenu(tr("main.presets"))
        self.pause_action: QAction | None = None
        if with_automation:
            self.pause_action = menu.addAction(tr("automation.pause"))
            self.pause_action.triggered.connect(lambda: self.automation_pause_requested.emit(not self._paused))
        menu.addSeparator()
        menu.addAction(tr("tray.show")).triggered.connect(self.show_requested.emit)
        menu.addAction(tr("tray.quit")).triggered.connect(self.quit_requested.emit)
        self._menu = menu  # referansı tut
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_requested.emit()

    def set_presets(self, presets: list[Preset]) -> None:
        """"Hazır ayarlar" alt menüsünü günceller (görünen yerleşik + kullanıcı ayarları)."""
        self.presets_menu.clear()
        for preset in presets:
            action = self.presets_menu.addAction(dot_icon(preset.swatch()), preset.name)
            action.triggered.connect(lambda _=False, key=preset.key: self.preset_requested.emit(key))
        self.presets_menu.setEnabled(bool(presets))

    def set_automation_paused(self, paused: bool) -> None:
        """Duraklatma durumunu menüye yansıtır: duraklatılmışsa seçenek "devam et" olur (sinyal göndermez)."""
        self._paused = paused
        if self.pause_action is not None:
            self.pause_action.setText(tr("tray.automation_resume") if paused else tr("automation.pause"))

    def show(self) -> None:
        self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def set_title(self, title: str) -> None:
        self._title = title
        self._tray.setToolTip(title)

    def set_tooltip(self, text: str) -> None:
        self._tray.setToolTip(f"{self._title} · {text}" if text else self._title)

    def notify(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
