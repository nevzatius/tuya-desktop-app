"""Sistem tepsisi simgesi ve menüsü."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController(QObject):
    power_requested = Signal(bool)
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, title: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(title)
        menu = QMenu()
        menu.addAction("Işığı aç").triggered.connect(lambda: self.power_requested.emit(True))
        menu.addAction("Işığı kapat").triggered.connect(lambda: self.power_requested.emit(False))
        menu.addSeparator()
        menu.addAction("Pencereyi göster").triggered.connect(self.show_requested.emit)
        menu.addAction("Çık").triggered.connect(self.quit_requested.emit)
        self._menu = menu  # referansı tut
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_requested.emit()

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
