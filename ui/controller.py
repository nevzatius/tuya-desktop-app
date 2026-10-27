"""Pencere, köprü ve cihaz deposunu birbirine bağlar (ışık değiştir/ekle/kaldır)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QInputDialog, QMessageBox, QWidget

import devices as dv
import light_core as lc

from .setup_dialog import SetupDialog


class AppController(QObject):
    def __init__(
        self,
        store: dv.DeviceStore,
        bridge,
        window,
        dialog_factory: Callable[..., SetupDialog] | None = None,
        confirm: Callable[[QWidget, str], bool] | None = None,
        ask_name: Callable[[QWidget, str], str | None] | None = None,
        tracker=None,
        heartbeat_ms: int = 30_000,
    ) -> None:
        super().__init__(window)
        self.store, self.bridge, self.window = store, bridge, window
        self._dialog_factory = dialog_factory or SetupDialog
        self._confirm = confirm or self._default_confirm
        self._ask_name = ask_name or self._default_ask_name
        self.tracker = tracker
        if tracker is not None:
            bridge.state.connect(tracker.on_state)
            bridge.connectedChanged.connect(tracker.on_connected)
            window.energy.wattsChanged.connect(self._on_watts)
            self._beat = QTimer(self)
            self._beat.setInterval(heartbeat_ms)
            self._beat.timeout.connect(tracker.heartbeat)
            self._beat.start()
        window.deviceChosen.connect(self.choose)
        window.addRequested.connect(self.add)
        window.renameRequested.connect(self.rename)
        window.removeRequested.connect(self.remove)
        self._sync_energy(store.current())
        self.refresh_menu()

    def _sync_energy(self, cfg: lc.Config | None) -> None:
        if self.tracker is not None:
            if cfg is None:
                self.tracker.release()
            else:
                self.tracker.set_device(cfg.device_id, cfg.watts)
        if cfg is not None:
            self.window.energy.set_device(cfg.device_id, cfg.watts)

    def _on_watts(self, value: float) -> None:
        cfg = self.store.current()
        if cfg is None:
            return
        cfg.watts = value
        self.store.save()
        if self.tracker is not None:
            self.tracker.watts = value
            self.tracker.on_state(self.bridge_state())  # yeni güçle devam et

    def bridge_state(self):
        """Son bilinen ışık durumu (istemciden)."""
        client = getattr(self.bridge, "client", None)
        return getattr(client, "state", None) or lc.LightState()

    @staticmethod
    def _default_confirm(parent: QWidget, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, "Odamdaki Işık", text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
        box.button(QMessageBox.StandardButton.Yes).setText("Kaldır")
        box.button(QMessageBox.StandardButton.No).setText("Vazgeç")
        return box.exec() == QMessageBox.StandardButton.Yes

    @staticmethod
    def _default_ask_name(parent: QWidget, current: str) -> str | None:
        text, ok = QInputDialog.getText(parent, "Adını değiştir", "Işığın adı:", text=current)
        return text if ok else None

    def refresh_menu(self) -> None:
        self.window.set_devices(self.store.devices(), self.store.selected)

    def _activate(self, cfg: lc.Config) -> None:
        self.store.select(cfg.device_id)
        self.store.save()
        self.bridge.set_device(cfg)
        self.window.set_device(cfg)
        self._sync_energy(cfg)
        self.refresh_menu()

    def choose(self, device_id: str) -> None:
        cfg = self.store.get(device_id)
        if cfg is not None and cfg.device_id != self.bridge.cfg.device_id:
            self._activate(cfg)

    def add(self) -> None:
        dialog = self._dialog_factory({d.device_id for d in self.store.devices()}, parent=self.window)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        new = dialog.added_devices()
        if not new:
            return
        for cfg in new:
            self.store.add(cfg)
        self.store.save()
        self._activate(new[0])  # eklenen ilk ışığa geç

    def rename(self) -> None:
        cfg = self.store.current()
        if cfg is None:
            return
        name = self._ask_name(self.window, cfg.name)
        if name and name.strip():
            self.store.rename(cfg.device_id, name)
            self.store.save()
            self.window.set_device(self.store.current())
            self.refresh_menu()

    def remove(self) -> None:
        cfg = self.store.current()
        if cfg is None or not self._confirm(self.window, f"“{cfg.name}” kaldırılsın mı? Anahtarı bu bilgisayardan silinir (ışığın kendisine dokunulmaz)."):
            return
        self.store.remove(cfg.device_id)
        self.store.save()
        nxt = self.store.current()
        if nxt is None:
            self.bridge.release_device()
            self._sync_energy(None)
            self.window.show_empty()
            self.refresh_menu()
            self.add()  # hiç ışık kalmadı: ekleme sihirbazı
            return
        self._activate(nxt)
