"""Arayüzü bloklamadan arka planda iş çalıştıran ortak iş parçacığı sınıfı."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

_LIVE_WORKERS: set[QThread] = set()  # iş parçacıkları pencere kapansa da bitene kadar yaşar


class Worker(QThread):
    """`func(*args)`'ı arka planda çalıştırır; sonuç `done`, hata `failed(mesaj, tür)` ile gelir."""

    done = Signal(object)
    failed = Signal(str, str)

    def __init__(self, func: Callable, args: tuple, explain: Callable[[Exception], tuple[str, str]]) -> None:
        super().__init__()
        self._func, self._args, self._explain = func, args, explain
        _LIVE_WORKERS.add(self)
        self.finished.connect(lambda: _LIVE_WORKERS.discard(self))

    def run(self) -> None:
        try:
            result = self._func(*self._args)
        except Exception as exc:  # noqa: BLE001
            message, kind = self._explain(exc)
            self.failed.emit(message, kind)
        else:
            self.done.emit(result)
