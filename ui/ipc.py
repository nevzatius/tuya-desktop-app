"""Çalışan uygulamayı komut satırından tetiklemek için yerel kanal (QLocalServer / QLocalSocket).

* Kanal yalnızca yerel kullanıcıya açıktır (`UserAccessOption`; Windows'ta adlandırılmış boru, Unix'te yalnızca
  sahibin erişebildiği soket). Ağdan erişilemez; kanal adı kullanıcı adını içerir.
* Mesajlar tek satır JSON'dur ve küçüktür (en çok 4 KB); gizli bilgi taşımaz. Geçersiz mesaj reddedilir.
* Sunucu yalnızca tek-örnek kilidini alan uygulamada çalışır; komut satırı istemcisi kilidi almaz.
"""

from __future__ import annotations

import getpass
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEventLoop, QObject, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket

import quick_cli as qc
from i18n import tr
from version import APP_NAME

LOGGER = logging.getLogger("tuya_light.ipc")

SERVER_PREFIX = "TuyaDesktopApp"
MAX_MESSAGE = 4096
IDLE_MS = 3000  # mesajını tamamlamayan bağlantı bu kadar sonra kesilir


def server_name(user: str | None = None) -> str:
    try:
        who = user if user is not None else getpass.getuser()
    except Exception:  # noqa: BLE001
        who = "user"
    return f"{SERVER_PREFIX}-{re.sub(r'[^A-Za-z0-9_.-]', '_', who or 'user')}"


# -- uygulama tarafı --------------------------------------------------------------------------------------


def make_handler(
    find_preset: Callable[[str], object | None],
    preset_names: Callable[[], list[str]],
    apply_preset: Callable[[str], object],
    set_power: Callable[[bool], object],
    has_light: Callable[[], bool],
) -> Callable[[dict], dict]:
    """Komutu uygulamaya çeviren işleyici; yanıt `{"ok": bool, "code": ...}` sözlüğüdür."""

    def handle(command: dict) -> dict:
        kind = command.get("cmd")
        if kind not in ("scene", "power"):
            return {"ok": False, "code": "bad_command"}
        if not has_light():
            return {"ok": False, "code": "no_light"}
        if kind == "scene":
            name = command.get("name")
            if not isinstance(name, str) or not name.strip():
                return {"ok": False, "code": "bad_command"}
            preset = find_preset(name)
            if preset is None:
                return {"ok": False, "code": "unknown_scene", "names": preset_names()}
            apply_preset(preset.key)
            return {"ok": True, "code": "ok", "name": preset.name}
        on = command.get("on")
        if not isinstance(on, bool):
            return {"ok": False, "code": "bad_command"}
        set_power(on)
        return {"ok": True, "code": "ok", "on": on}

    return handle


class CommandServer(QObject):
    def __init__(self, handler: Callable[[dict], dict], name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._handler = handler
        self.name = name or server_name()
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)  # yalnızca bu kullanıcı
        self._server.newConnection.connect(self._on_connection)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    def start(self) -> bool:
        QLocalServer.removeServer(self.name)  # önceki çalışmadan kalan soket dosyası (Unix)
        ok = self._server.listen(self.name)
        if not ok:
            LOGGER.warning("could not listen on the local command channel: %s", self._server.errorString())
        return ok

    def close(self) -> None:
        self._server.close()

    def user_only(self) -> bool:
        return bool(self._server.socketOptions() & QLocalServer.SocketOption.UserAccessOption)

    def _on_connection(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._on_ready(s))
            socket.disconnected.connect(lambda s=socket: self._forget(s))
            QTimer.singleShot(IDLE_MS, lambda s=socket: self._expire(s))

    def _forget(self, socket: QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        try:
            socket.deleteLater()
        except RuntimeError:  # Qt nesneyi zaten sildi
            pass

    def _expire(self, socket: QLocalSocket) -> None:
        if socket in self._buffers:  # hâlâ bekleyen: mesajını tamamlamadı
            socket.abort()

    def _on_ready(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.get(socket)
        if buffer is None:
            return
        buffer += bytes(socket.readAll())
        if b"\n" not in buffer and len(buffer) <= MAX_MESSAGE:
            return  # satır henüz tamamlanmadı
        if len(buffer) > MAX_MESSAGE and b"\n" not in buffer[:MAX_MESSAGE]:
            self._reply(socket, {"ok": False, "code": "bad_command"})
            return
        line = bytes(buffer.split(b"\n", 1)[0])
        try:
            command = json.loads(line.decode("utf-8"))
            if not isinstance(command, dict):
                raise ValueError("not an object")
            response = self._handler(command)
        except (ValueError, UnicodeDecodeError):
            response = {"ok": False, "code": "bad_command"}
        except Exception:  # noqa: BLE001 - işleyici hatası uygulamayı bozmasın
            LOGGER.exception("command handler failed")
            response = {"ok": False, "code": "error"}
        self._reply(socket, response)

    def _reply(self, socket: QLocalSocket, response: dict) -> None:
        self._buffers.pop(socket, None)
        socket.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")
        socket.flush()
        socket.disconnectFromServer()


# -- komut satırı tarafı ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reply:
    exit_code: int
    text: str


def describe(command: qc.QuickCommand, response: dict) -> str:
    code = response.get("code")
    if response.get("ok"):
        if command.kind == "scene":
            return tr("cli.done_scene", name=response.get("name") or command.payload.get("name", ""))
        return tr("cli.done_power_on" if command.payload.get("on") else "cli.done_power_off")
    if code == "unknown_scene":
        names = ", ".join(str(n) for n in response.get("names", []))
        return tr("cli.unknown_scene", name=command.payload.get("name", ""), names=names)
    if code == "no_light":
        return tr("cli.no_light")
    return tr("cli.rejected")


def send_command(command: qc.QuickCommand, name: str | None = None, timeout_ms: int = 3000) -> Reply:
    """Komutu çalışan uygulamaya iletir (yanıt gelene ya da süre dolana kadar bekler). Uygulama çalışmıyorsa
    anlaşılır hata ve çıkış kodu döner.

    Engelleyici `waitFor*` çağrıları yerine olay döngüsü kullanılır: Windows'ta bunlar yazmayı geç tamamlayabilir.
    """
    loop = QEventLoop()
    socket = QLocalSocket()
    timer = QTimer()
    timer.setSingleShot(True)
    state = {"connected": False}
    data = bytearray()

    def on_connected() -> None:
        state["connected"] = True
        socket.write(json.dumps(command.payload, ensure_ascii=False).encode("utf-8") + b"\n")
        socket.flush()

    def on_ready() -> None:
        data.extend(bytes(socket.readAll()))
        if b"\n" in data:
            loop.quit()

    def on_error(*_args) -> None:
        if not state["connected"]:  # sunucu yok / reddedildi
            loop.quit()

    socket.connected.connect(on_connected)
    socket.readyRead.connect(on_ready)
    socket.errorOccurred.connect(on_error)
    socket.disconnected.connect(loop.quit)
    timer.timeout.connect(loop.quit)
    socket.connectToServer(name or server_name())
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()
    connected = state["connected"]
    socket.abort()
    if not connected:
        return Reply(qc.EXIT_NOT_RUNNING, tr("cli.not_running", app=APP_NAME))
    try:
        response = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
        if not isinstance(response, dict):
            raise ValueError("not an object")
    except (ValueError, UnicodeDecodeError):
        return Reply(qc.EXIT_NO_REPLY, tr("cli.no_reply"))
    return Reply(qc.EXIT_OK if response.get("ok") else qc.EXIT_REJECTED, describe(command, response))
