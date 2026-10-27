"""Genel kısayol tuşları (yalnızca Windows): her hazır ayara bir tuş kombinasyonu.

`RegisterHotKey` (ctypes) ile kaydedilir; ek bağımlılık yoktur. macOS/Linux'ta özellik yoktur ve arayüzde gizlenir.
Kombinasyon çözümleme `shortcuts.py`'dedir. Başka bir uygulama aynı kombinasyonu kullanıyorsa kayıt başarısız olur
ve kullanıcıya hata gösterilir.
"""

from __future__ import annotations

import ctypes
import logging
import sys
from typing import Protocol

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from shortcuts import MOD_NOREPEAT, HotkeyError, parse_combo

LOGGER = logging.getLogger("tuya_light.hotkeys")

WM_HOTKEY = 0x0312
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
BASE_ID = 0xB000  # uygulamaya ait kısayol numaraları


class HotkeyBackend(Protocol):
    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        """0 = başarılı; aksi halde hata kodu (1409 = başkası kullanıyor)."""

    def unregister(self, hotkey_id: int) -> None: ...


class WindowsBackend:
    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)  # type: ignore[attr-defined]

    def register(self, hotkey_id: int, mods: int, vk: int) -> int:
        ok = self._user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk)
        return 0 if ok else (ctypes.get_last_error() or 1)  # type: ignore[attr-defined]

    def unregister(self, hotkey_id: int) -> None:
        self._user32.UnregisterHotKey(None, hotkey_id)


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, on_hotkey) -> None:
        super().__init__()
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if bytes(event_type) == b"windows_generic_MSG":
            import ctypes.wintypes  # yalnızca Windows'ta gerekir

            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                self._on_hotkey(int(msg.wParam))
        return False, 0


class HotkeyManager(QObject):
    """Kısayolları kaydeder ve basılınca `triggered(hazır ayar kimliği)` gönderir."""

    triggered = Signal(str)

    def __init__(self, backend: HotkeyBackend | None = None, available: bool | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.available = sys.platform == "win32" if available is None else available
        self._backend = backend
        self._by_id: dict[int, str] = {}
        self._filter: _Filter | None = None

    def _ensure_backend(self) -> HotkeyBackend:
        if self._backend is None:
            self._backend = WindowsBackend()
        return self._backend

    def apply(self, bindings: dict[str, str]) -> dict[str, str]:
        """Tüm kayıtları bırakıp `bindings` (hazır ayar kimliği -> kombinasyon) kadarını kaydeder.

        Başarısız olanları döndürür: kimlik -> "invalid" | "needs_modifier" | "conflict" | "failed".
        """
        errors: dict[str, str] = {}
        if not self.available:
            return errors
        backend = self._ensure_backend()
        for hotkey_id in list(self._by_id):
            backend.unregister(hotkey_id)
        self._by_id.clear()
        for offset, (key, combo) in enumerate(sorted(bindings.items())):
            try:
                mods, vk, _ = parse_combo(combo)
            except HotkeyError as exc:
                errors[key] = exc.code
                continue
            hotkey_id = BASE_ID + offset
            code = backend.register(hotkey_id, mods, vk)
            if code == 0:
                self._by_id[hotkey_id] = key
            else:
                errors[key] = "conflict" if code == ERROR_HOTKEY_ALREADY_REGISTERED else "failed"
                LOGGER.info("hotkey could not be registered (error %s)", code)
        self._install_filter()
        return errors

    def _install_filter(self) -> None:
        if self._filter is None and self._by_id:
            app = QCoreApplication.instance()
            if app is not None:
                self._filter = _Filter(self.handle)
                app.installNativeEventFilter(self._filter)

    def handle(self, hotkey_id: int) -> None:
        key = self._by_id.get(hotkey_id)
        if key is not None:
            self.triggered.emit(key)

    def shutdown(self) -> None:
        if self._backend is not None:
            for hotkey_id in list(self._by_id):
                self._backend.unregister(hotkey_id)
        self._by_id.clear()
        app = QCoreApplication.instance()
        if self._filter is not None and app is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
