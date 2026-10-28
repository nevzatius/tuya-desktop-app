"""Parlaklık / beyaz sıcaklığı / renk çarkı düzenleyicisi: hazır ayar ve otomasyon pencerelerinde ortak kullanılır."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from i18n import tr

from .colors import COOL, NEUTRAL, WARM, hex_of, hs_rgb, shade
from .widgets import ColorWheel, GradientSlider

KINDS = ("brightness", "white", "colour", "scene")  # hangi denetimlerin görüneceği


class SceneEditor(QWidget):
    """`kind`: "brightness" yalnızca parlaklık; "white" parlaklık + sıcaklık; "colour" parlaklık + çark;
    "scene" beyaz/renk anahtarı ile ikisinden biri."""

    changed = Signal()

    def __init__(self, kind: str = "scene", wheel_size: int = 190, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "white"
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)

        self.seg_wrap = QFrame()
        self.seg_wrap.setObjectName("segWrap")
        seg_row = QHBoxLayout(self.seg_wrap)
        seg_row.setContentsMargins(4, 4, 4, 4)
        seg_row.setSpacing(4)
        self.seg_white, self.seg_colour = QPushButton(tr("main.white")), QPushButton(tr("main.colour"))
        group = QButtonGroup(self)
        for button, mode in ((self.seg_white, "white"), (self.seg_colour, "colour")):
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button)
            seg_row.addWidget(button, 1)
            button.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
        self._group = group
        box.addWidget(self.seg_wrap)

        self.bright_label = QLabel()
        self.bright_label.setObjectName("value")
        self.bright = GradientSlider(fill=True)
        self.bright.setRange(1, 100)
        self.bright.setValue(50)
        self._bright_row = self._row(tr("main.brightness"), self.bright_label, self.bright)
        box.addWidget(self._bright_row)

        self.temp_label = QLabel()
        self.temp_label.setObjectName("value")
        self.temp = GradientSlider([(0.0, WARM), (0.5, NEUTRAL), (1.0, COOL)])
        self.temp.setRange(0, 100)
        self._temp_row = self._row(tr("main.temperature"), self.temp_label, self.temp)
        box.addWidget(self._temp_row)

        self.wheel = ColorWheel(wheel_size)
        self.hex_label = QLabel()
        self.hex_label.setObjectName("hex")
        self._wheel_row = QWidget()
        wheel_box = QVBoxLayout(self._wheel_row)
        wheel_box.setContentsMargins(0, 0, 0, 0)
        wheel_box.setSpacing(4)
        wheel_box.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        wheel_box.addWidget(self.hex_label, 0, Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(self._wheel_row)

        self.bright.valueChanged.connect(self._on_value)
        self.temp.valueChanged.connect(self._on_value)
        self.wheel.changed.connect(lambda *_: self._on_value())
        self.kind = kind
        self.set_kind(kind)
        self._refresh_labels()

    @staticmethod
    def _row(title: str, value_label: QLabel, slider: GradientSlider) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        head = QHBoxLayout()
        caption = QLabel(title)
        caption.setObjectName("muted")
        head.addWidget(caption)
        head.addStretch()
        head.addWidget(value_label)
        lay.addLayout(head)
        lay.addWidget(slider)
        return holder

    # -- görünüm ---------------------------------------------------------------

    def set_kind(self, kind: str) -> None:
        self.kind = kind if kind in KINDS else "scene"
        if self.kind == "white":
            self._mode = "white"
        elif self.kind == "colour":
            self._mode = "colour"
        self._relayout()

    def _relayout(self) -> None:
        self.seg_wrap.setVisible(self.kind == "scene")
        self._bright_row.setVisible(True)
        self._temp_row.setVisible(self._mode == "white" and self.kind in ("white", "scene"))
        self._wheel_row.setVisible(self._mode == "colour" and self.kind in ("colour", "scene"))
        (self.seg_colour if self._mode == "colour" else self.seg_white).setChecked(True)

    def set_mode(self, mode: str) -> None:
        if mode in ("white", "colour") and self.kind == "scene":
            self._mode = mode
            self._relayout()
            self.changed.emit()

    def mode(self) -> str:
        return self._mode

    # -- değerler --------------------------------------------------------------

    def values(self) -> dict[str, object]:
        hue, sat = self.wheel.hs()
        return {"mode": self._mode, "bright": self.bright.value(), "temp": self.temp.value(), "hue": hue, "sat": sat}

    def set_values(self, mode: str = "white", bright: int = 50, temp: int = 0, hue: int = 0, sat: int = 0) -> None:
        for widget in (self.bright, self.temp):
            widget.blockSignals(True)
        try:
            self.bright.setValue(int(bright))
            self.temp.setValue(int(temp))
            self.wheel.set_hs(int(hue), int(sat))
        finally:
            for widget in (self.bright, self.temp):
                widget.blockSignals(False)
        if self.kind == "scene" and mode in ("white", "colour"):
            self._mode = mode
        self._relayout()
        self._refresh_labels()

    def _on_value(self) -> None:
        self._refresh_labels()
        self.changed.emit()

    def _refresh_labels(self) -> None:
        self.bright_label.setText(tr("fmt.percent", value=self.bright.value()))
        value = self.temp.value()
        self.temp_label.setText(tr("main.warm") if value < 34 else tr("main.neutral") if value < 67 else tr("main.cool"))
        hue, sat = self.wheel.hs()
        self.hex_label.setText(hex_of(hs_rgb(hue, sat)))
        accent = hs_rgb(hue, sat) if self._mode == "colour" else WARM
        self.bright.set_stops([(0.0, shade(accent, 0.30)), (1.0, accent)])
