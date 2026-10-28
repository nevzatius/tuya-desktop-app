"""Qt testleri için ortak sahte köprü: MainWindow'un beklediği sinyaller ve komut kaydı."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class FakeBridge(QObject):
    state = Signal(object)
    status = Signal(str)
    error = Signal(str)
    problem = Signal(str)
    log = Signal(str)
    connectedChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def set_power(self, on):
        self.calls.append(("power", on))

    def apply_scene(self, preset):
        self.calls.append(("scene", preset.name))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None
