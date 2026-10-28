"""Uygulama günlüğü: veri klasöründe dönen `app.log` (~1 MB x 3 dosya).

Dosyaya yazılan HER satır (iz kayıtları dahil) `privacy.redact` ile maskelenir: bilinen yerel anahtar, cihaz kimliği, uuid ve MAC
değerleri ile MAC/GUID/uzun onaltılık kalıplar dosyaya hiç düşmez. Tanılama raporu bu dosyanın son satırlarını da içerir (`tail`).
Qt'ye bağlı değildir.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable, Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path

import devices
from privacy import redact

FILE_NAME = "app.log"
MAX_BYTES = 1_000_000
BACKUPS = 2  # app.log + app.log.1 + app.log.2 = 3 dosya
TAIL_LINES = 50
_TAIL_READ_BYTES = 128_000  # dosyanın yalnızca sonu okunur
_MARK = "_tuya_applog"

SecretsProvider = Callable[[], Iterable[str]]


def log_path() -> Path:
    return devices.user_data_dir() / FILE_NAME


class RedactingFormatter(logging.Formatter):
    """Biçimlenmiş satırı (mesaj + hata izi) yazılmadan önce maskeler; gizli değerler her kayıtta yeniden sorulur."""

    def __init__(self, secrets: SecretsProvider | None = None) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._secrets = secrets or (lambda: ())

    def format(self, record: logging.LogRecord) -> str:
        try:
            secrets = list(self._secrets())
        except Exception:  # noqa: BLE001 - bilinen değerler alınamasa da kalıp maskesi yine uygulanır
            secrets = []
        return redact(super().format(record), secrets)


def setup(
    path: Path | None = None,
    secrets: SecretsProvider | None = None,
    level: int = logging.INFO,
    max_bytes: int = MAX_BYTES,
    backups: int = BACKUPS,
) -> RotatingFileHandler | None:
    """Kök günlükçüye dönen dosya işleyicisini ekler (tekrar çağrılırsa eskisinin yerine geçer). Dosya açılamazsa None."""
    root = logging.getLogger()
    for old in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(old)
        old.close()
    target = Path(path) if path is not None else log_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(target, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True)
    except OSError:
        return None  # günlük yazılamıyorsa uygulama yine de çalışsın
    handler.setFormatter(RedactingFormatter(secrets))
    handler.setLevel(level)
    setattr(handler, _MARK, True)
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    return handler


def shutdown() -> None:
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(handler)
        handler.close()


def install_excepthooks() -> None:
    """Yakalanmayan hatalar (ana ve diğer iş parçacıkları) günlüğe düşer; sonra özgün kanca çalışır."""
    logger = logging.getLogger("tuya_light.crash")
    previous = sys.excepthook

    def hook(exc_type, exc, tb) -> None:
        logger.critical("uncaught exception", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = hook
    previous_thread = threading.excepthook

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        logger.critical("uncaught exception in thread %s", getattr(args.thread, "name", "?"), exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        previous_thread(args)

    threading.excepthook = thread_hook


def _read_tail(path: Path) -> list[str]:
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_READ_BYTES))
            data = handle.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    return lines[1:] if size > _TAIL_READ_BYTES and lines else lines  # ilk satır kesik olabilir


def tail(n: int = TAIL_LINES, path: Path | None = None, secrets: Iterable[str] = ()) -> list[str]:
    """Günlüğün son `n` satırı (eskiden yeniye); gerekirse bir önceki (döndürülmüş) dosyadan tamamlanır. Okurken yeniden maskelenir."""
    base = Path(path) if path is not None else log_path()
    lines: list[str] = []
    for candidate in (base.with_name(f"{base.name}.1"), base):  # eski -> yeni
        lines += _read_tail(candidate)
    secrets = list(secrets)
    return [redact(line, secrets) for line in lines[-n:]]
