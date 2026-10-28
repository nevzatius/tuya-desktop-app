"""Çalışan uygulamayı komut satırından tetikleme: `light_app.py --scene "Film"` ve `--power on|off`.

Bu modül yalnızca argümanları çözümler (Qt'den bağımsız). Komutu çalışan uygulamaya iletmek `ui/ipc.py`'dedir.

Çıkış kodları: 0 komut uygulamaya iletildi · 1 uygulama reddetti (ör. hazır ayar yok) · 2 uygulama çalışmıyor ·
3 uygulamadan yanıt alınamadı · 64 komut satırı hatalı.
"""

from __future__ import annotations

from dataclasses import dataclass

EXIT_OK, EXIT_REJECTED, EXIT_NOT_RUNNING, EXIT_NO_REPLY, EXIT_USAGE = 0, 1, 2, 3, 64


class UsageError(ValueError):
    """Komut satırı hatalı; `code`: "both" | "missing" | "power_value" | "empty_scene"."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class QuickCommand:
    payload: dict  # yerel kanala gönderilecek komut

    @property
    def kind(self) -> str:
        return str(self.payload.get("cmd", ""))


HELP = "help"


def _value(argv: list[str], index: int, flag: str) -> tuple[str, int]:
    """(değer, tüketilen argüman sayısı): `--flag değer` ya da `--flag=değer`."""
    arg = argv[index]
    if arg.startswith(flag + "="):
        return arg[len(flag) + 1 :], 1
    if index + 1 >= len(argv):
        raise UsageError("missing")
    return argv[index + 1], 2


def parse(argv: list[str]) -> QuickCommand | str | None:
    """`argv` (program adı dahil) -> komut, `HELP` ya da hızlı komut yoksa None. Bilinmeyen argümanlar (--minimized) yok sayılır."""
    scene: str | None = None
    power: str | None = None
    args = argv[1:]
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-h", "--help"):
            return HELP
        if arg == "--scene" or arg.startswith("--scene="):
            scene, used = _value(args, index, "--scene")
            index += used
        elif arg == "--power" or arg.startswith("--power="):
            power, used = _value(args, index, "--power")
            index += used
        else:
            index += 1
    if scene is None and power is None:
        return None
    if scene is not None and power is not None:
        raise UsageError("both")
    if scene is not None:
        if not scene.strip():
            raise UsageError("empty_scene")
        return QuickCommand({"cmd": "scene", "name": scene.strip()})
    if power.strip().lower() not in ("on", "off"):
        raise UsageError("power_value")
    return QuickCommand({"cmd": "power", "on": power.strip().lower() == "on"})
