"""Enerji sekmesi: günlük / haftalık / aylık tahmini tüketim ve TL maliyeti."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

import energy as en

from .theme import BORDER, MUTED, TEXT

PERIOD_TITLES = {"day": "BUGÜN", "week": "SON 7 GÜN", "month": "SON 30 GÜN"}
PERIOD_TABS = (("day", "Gün"), ("week", "Hafta"), ("month", "Ay"))


class BarChart(QWidget):
    """Basit çubuk grafik: üzerine gelince değer ipucu, güncel çubuk vurgulu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self._buckets: list[en.Bucket] = []
        self._price = en.DEFAULT_PRICE_TL
        self._current = -1
        self._accent = QColor(255, 196, 92)
        self._hover = -1

    def set_data(self, buckets: list[en.Bucket], price: float, current: int) -> None:
        self._buckets, self._price, self._current = buckets, price, current
        self.update()

    def _plot(self) -> QRectF:
        return QRectF(4, 8, self.width() - 8, self.height() - 30)

    def _index_at(self, x: float) -> int:
        if not self._buckets:
            return -1
        plot = self._plot()
        i = math.floor((x - plot.left()) / (plot.width() / len(self._buckets)))
        return i if 0 <= i < len(self._buckets) else -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        i = self._index_at(event.position().x())
        if i != self._hover:
            self._hover = i
            self.update()
        if i >= 0:
            b = self._buckets[i]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{b.label}: {en.fmt_kwh(b.kwh)} · {en.fmt_tl(b.kwh * self._price)}\n{en.fmt_duration(b.seconds)} açık",
                self,
            )

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        n = len(self._buckets)
        grid = QPen(QColor(BORDER))
        grid.setWidthF(1)
        p.setPen(grid)
        p.drawLine(QPointF(plot.left(), plot.bottom()), QPointF(plot.right(), plot.bottom()))
        if n == 0:
            return
        peak = max((b.kwh for b in self._buckets), default=0.0)
        slot = plot.width() / n
        bar_w = max(2.0, slot * 0.62)
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        p.setFont(font)
        step = 1 if n <= 7 else (3 if n <= 24 else 5)
        for i, b in enumerate(self._buckets):
            cx = plot.left() + slot * (i + 0.5)
            height = 0.0 if peak <= 0 else (b.kwh / peak) * (plot.height() - 6)
            if b.kwh > 0:
                height = max(height, 3.0)
            rect = QRectF(cx - bar_w / 2, plot.bottom() - height, bar_w, height)
            strong = i == self._current or i == self._hover
            top = QColor(self._accent)
            bottom = QColor(self._accent).darker(170)
            if not strong:
                top.setAlphaF(0.55)
                bottom.setAlphaF(0.45)
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0, top)
            grad.setColorAt(1, bottom)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            if height > 0:
                p.drawRoundedRect(rect, min(3.0, bar_w / 2), min(3.0, bar_w / 2))
            if i % step == 0 or i == n - 1 and n <= 7:
                p.setPen(QColor(TEXT if i == self._current else MUTED))
                p.drawText(QRectF(cx - slot * step / 2, plot.bottom() + 4, slot * step, 18), Qt.AlignmentFlag.AlignCenter, b.label)


class EnergyPage(QWidget):
    wattsChanged = Signal(float)
    priceChanged = Signal(float)

    def __init__(self, settings: QSettings, log: en.EnergyLog | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._log = log
        self._period = "day"
        self._device = ""
        self._clock = time.time
        try:
            price = float(settings.value("energy/price", en.DEFAULT_PRICE_TL))
        except (TypeError, ValueError):
            price = en.DEFAULT_PRICE_TL
        self._price = price if price > 0 else en.DEFAULT_PRICE_TL
        self._build()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self.refresh)

    # ------------------------------------------------------------- yapı

    def _build(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        seg_wrap = QFrame()
        seg_wrap.setObjectName("segWrap")
        seg = QHBoxLayout(seg_wrap)
        seg.setContentsMargins(4, 4, 4, 4)
        seg.setSpacing(4)
        self._group = QButtonGroup(self)
        self.period_buttons: dict[str, QPushButton] = {}
        for key, text in PERIOD_TABS:
            button = QPushButton(text)
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.set_period(k))
            self._group.addButton(button)
            seg.addWidget(button)
            self.period_buttons[key] = button
        self.period_buttons["day"].setChecked(True)
        lay.addWidget(seg_wrap)

        hero = QVBoxLayout()
        hero.setSpacing(2)
        self.period_title = QLabel(PERIOD_TITLES["day"])
        self.period_title.setObjectName("cardTitle")
        self.period_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cost_label = QLabel(en.fmt_tl(0))
        self.cost_label.setObjectName("stateBig")
        self.cost_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("sub")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(self.period_title)
        hero.addWidget(self.cost_label)
        hero.addWidget(self.detail_label)
        lay.addLayout(hero)

        chart_card = QFrame()
        chart_card.setObjectName("card")
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(14, 14, 14, 10)
        self.chart = BarChart()
        cl.addWidget(self.chart)
        lay.addWidget(chart_card)

        self.all_label = QLabel("")
        self.all_label.setObjectName("muted")
        self.all_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.all_label.hide()
        lay.addWidget(self.all_label)

        settings_card = QFrame()
        settings_card.setObjectName("card")
        sl = QVBoxLayout(settings_card)
        sl.setContentsMargins(18, 16, 18, 16)
        sl.setSpacing(10)
        title = QLabel("TAHMİN AYARLARI")
        title.setObjectName("cardTitle")
        sl.addWidget(title)
        self.watts = QDoubleSpinBox()
        self.watts.setRange(0.5, 2000)
        self.watts.setDecimals(1)
        self.watts.setSingleStep(0.5)
        self.watts.setSuffix(" W")
        self.price = QDoubleSpinBox()
        self.price.setRange(0.01, 1000)
        self.price.setDecimals(2)
        self.price.setSingleStep(0.1)
        self.price.setPrefix("₺ ")
        self.price.setSuffix(" / kWh")
        self.price.setValue(self._price)
        for label_text, spin in (("Işığın gücü (tam parlaklıkta)", self.watts), ("Elektrik birim fiyatı", self.price)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            row.addStretch()
            spin.setFixedWidth(130)
            row.addWidget(spin)
            sl.addLayout(row)
        note = QLabel(f"{en.PRICE_NOTE}<br>Işığın gücü ambalajında ya da ürün sayfasında yazar (ör. 9 W).")
        note.setObjectName("muted")
        note.setWordWrap(True)
        sl.addWidget(note)
        lay.addWidget(settings_card)

        disclaimer = QLabel(
            "Bu değerler <b>tahmindir</b>: ışık güç ölçmez; güç × parlaklık × açık kalma süresi hesaplanır. "
            "Yalnızca uygulama açıkken ve ışığa bağlıyken kaydedilir; telefon ya da duvar anahtarıyla yapılan "
            "değişiklikler bağlantı kesikken görülmez."
        )
        disclaimer.setObjectName("muted")
        disclaimer.setWordWrap(True)
        lay.addWidget(disclaimer)
        lay.addStretch()

        self.watts.valueChanged.connect(self._on_watts)
        self.price.valueChanged.connect(self._on_price)

    # ------------------------------------------------------------- olaylar

    def set_log(self, log: en.EnergyLog | None) -> None:
        self._log = log
        self.refresh()

    def set_device(self, device_id: str, watts: float) -> None:
        self._device = device_id
        self.watts.blockSignals(True)
        self.watts.setValue(watts)
        self.watts.blockSignals(False)
        self.refresh()

    def set_period(self, period: str) -> None:
        if period in en.PERIODS:
            self._period = period
            self.period_buttons[period].setChecked(True)
            self.refresh()

    def _on_watts(self, value: float) -> None:
        self.wattsChanged.emit(value)

    def _on_price(self, value: float) -> None:
        self._price = value
        self._settings.setValue("energy/price", value)
        self.priceChanged.emit(value)
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    # ------------------------------------------------------------- gösterim

    @property
    def price_value(self) -> float:
        return self._price

    def refresh(self) -> None:
        self.period_title.setText(PERIOD_TITLES[self._period])
        if self._log is None:
            self.cost_label.setText(en.fmt_tl(0))
            self.detail_label.setText("Kayıt yok")
            self.chart.set_data([], self._price, -1)
            self.all_label.hide()
            return
        now = self._clock()
        summary = en.summarize(self._log, self._period, self._price, self._device or None, now)
        self.cost_label.setText(en.fmt_tl(summary.cost_tl))
        self.detail_label.setText(f"{en.fmt_kwh(summary.kwh)} · {en.fmt_duration(summary.seconds)} açık")
        current = len(summary.buckets) - 1 if self._period != "day" else next(
            (i for i, b in enumerate(summary.buckets) if b.start <= now < b.end), -1
        )
        self.chart.set_data(summary.buckets, self._price, current)
        total = en.summarize(self._log, self._period, self._price, None, now)
        more = total.kwh > summary.kwh + 1e-9  # başka ışıkların da kaydı var
        self.all_label.setText(f"Tüm ışıklar: {en.fmt_tl(total.cost_tl)} · {en.fmt_kwh(total.kwh)}" if more else "")
        self.all_label.setVisible(more)
