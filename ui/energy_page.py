"""Enerji sekmesi: günlük / haftalık / aylık tahmini tüketim ve TL maliyeti."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QLocale, QPointF, QRectF, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
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
import i18n
from i18n import tr

from .theme import BORDER, MUTED, TEXT

PERIOD_KEYS = ("day", "week", "month")


def period_title(period: str) -> str:
    return tr(f"energy.period_{period}")


class BarChart(QWidget):
    """Basit çubuk grafik: üzerine gelince değer ipucu, güncel çubuk vurgulu."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self._buckets: list[en.Bucket] = []
        self._price = 0.0
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
            parts = [en.fmt_kwh(b.kwh)]
            if self._price > 0:
                parts.append(en.fmt_money(b.kwh * self._price))
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{b.label}: {' · '.join(parts)}\n{tr('energy.tip_duration', duration=en.fmt_duration(b.seconds))}",
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
        self._turkish = i18n.language() == "tr"
        # Fiyat dile özeldir: Türkçede eski anahtar (₺), diğer dillerde ayrı anahtar ve seçilebilir para birimi.
        self._price_key = "energy/price" if self._turkish else "energy/price_en"
        if not self._turkish:
            i18n.set_currency(str(settings.value("energy/currency", "")) or i18n.system_currency())
        fallback = en.default_price()
        try:
            price = float(settings.value(self._price_key, fallback))
        except (TypeError, ValueError):
            price = fallback
        self._price = price if price > 0 else fallback
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
        for key in PERIOD_KEYS:
            button = QPushButton(tr(f"energy.tab_{key}"))
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
        self.period_title = QLabel(period_title("day"))
        self.period_title.setObjectName("cardTitle")
        self.period_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cost_label = QLabel(self._money(0))
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
        title = QLabel(i18n.upper(tr("energy.settings_title")))
        title.setObjectName("cardTitle")
        sl.addWidget(title)
        self.watts = QDoubleSpinBox()
        self.watts.setRange(0.5, 2000)
        self.watts.setDecimals(1)
        self.watts.setSingleStep(0.5)
        self.watts.setSuffix(" W")
        self.price = QDoubleSpinBox()
        self.price.setDecimals(2)
        self.price.setSingleStep(0.1)
        self.price.setSuffix(" / kWh")
        if self._turkish:
            self.price.setRange(0.01, 1000)
        else:  # fiyat elle girilir: 0 = girilmedi
            self.price.setRange(0.0, 1000)
            self.price.setSpecialValueText(tr("energy.price_unset"))
        self.price.setValue(self._price)
        # Sayı biçimi (virgül/nokta) arayüz diline uysun, sistem bölgesine değil.
        locale = QLocale(QLocale.Language.Turkish if self._turkish else QLocale.Language.English)
        for spin in (self.watts, self.price):
            spin.setLocale(locale)
        self.currency = QComboBox()
        for code, symbol in i18n.CURRENCIES.items():
            self.currency.addItem(f"{code} ({symbol})", code)
        self.currency.setCurrentIndex(max(0, self.currency.findData(i18n.currency_code())))
        self.currency.currentIndexChanged.connect(self._on_currency)
        self._update_price_prefix()
        rows = [(tr("energy.watts_label"), self.watts), (tr("energy.price_label"), self.price)]
        if not self._turkish:
            rows.append((tr("energy.currency_label"), self.currency))
        for label_text, spin in rows:
            row = QHBoxLayout()
            row.addWidget(QLabel(label_text))
            row.addStretch()
            spin.setFixedWidth(130)
            row.addWidget(spin)
            sl.addLayout(row)
        note = QLabel(f"{tr('energy.price_note')}<br>{tr('energy.watts_hint')}")
        note.setObjectName("muted")
        note.setWordWrap(True)
        sl.addWidget(note)
        lay.addWidget(settings_card)

        disclaimer = QLabel(tr("energy.disclaimer"))
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

    def _money(self, value: float) -> str:
        """Fiyat girilmemişse (İngilizce, ilk açılış) tutar yerine çizgi gösterilir."""
        return en.fmt_money(value) if self._price > 0 else "—"

    def _update_price_prefix(self) -> None:
        self.price.setPrefix(f"{i18n.currency_symbol()} ")

    def _on_currency(self) -> None:
        code = self.currency.currentData()
        i18n.set_currency(code)
        self._settings.setValue("energy/currency", code)
        self._update_price_prefix()
        self.refresh()

    def _on_price(self, value: float) -> None:
        self._price = value
        self._settings.setValue(self._price_key, value)
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
        self.period_title.setText(period_title(self._period))
        if self._log is None:
            self.cost_label.setText(self._money(0))
            self.detail_label.setText(tr("energy.no_records"))
            self.chart.set_data([], self._price, -1)
            self.all_label.hide()
            return
        now = self._clock()
        summary = en.summarize(self._log, self._period, self._price, self._device or None, now)
        self.cost_label.setText(self._money(summary.cost_tl))
        self.detail_label.setText(
            tr("energy.detail", kwh=en.fmt_kwh(summary.kwh), duration=en.fmt_duration(summary.seconds))
        )
        current = len(summary.buckets) - 1 if self._period != "day" else next(
            (i for i, b in enumerate(summary.buckets) if b.start <= now < b.end), -1
        )
        self.chart.set_data(summary.buckets, self._price, current)
        total = en.summarize(self._log, self._period, self._price, None, now)
        more = total.kwh > summary.kwh + 1e-9  # başka ışıkların da kaydı var
        if self._price > 0:
            all_text = tr("energy.all_lights", cost=en.fmt_money(total.cost_tl), kwh=en.fmt_kwh(total.kwh))
        else:
            all_text = tr("energy.all_lights_nocost", kwh=en.fmt_kwh(total.kwh))
        self.all_label.setText(all_text if more else "")
        self.all_label.setVisible(more)
