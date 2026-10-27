"""Özel çizilmiş bileşenler: güç düğmesi, gradyan kaydırıcı, renk çarkı."""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QSlider, QWidget

from .colors import RGB, hs_rgb, shade


def qcolor(rgb: RGB, alpha: float = 1.0) -> QColor:
    color = QColor(*rgb)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


class StatusPill(QWidget):
    """Bağlantı durumunu gösteren, noktalı ve tam yuvarlak köşeli etiket."""

    TONES: dict[str, RGB] = {
        "ok": (61, 220, 151),
        "warn": (255, 180, 84),
        "bad": (255, 107, 107),
        "idle": (139, 148, 168),
    }
    PAD_LEFT, DOT, GAP, PAD_RIGHT, HEIGHT = 13, 7, 7, 15, 28

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._tone = "idle"
        font = self.font()
        font.setPointSizeF(max(font.pointSizeF() - 0.5, 8.0))
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def text(self) -> str:
        return self._text

    def tone(self) -> str:
        return self._tone

    def set_status(self, text: str, tone: str) -> None:
        self._text = text
        self._tone = tone if tone in self.TONES else "idle"
        self.setToolTip(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        text_width = self.fontMetrics().horizontalAdvance(self._text)
        return QSize(self.PAD_LEFT + self.DOT + self.GAP + text_width + self.PAD_RIGHT, self.HEIGHT)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rgb = self.TONES[self._tone]
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(qcolor(rgb, 0.12))
        p.setPen(QPen(qcolor(rgb, 0.30), 1.0))
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qcolor(rgb))
        p.drawEllipse(QPointF(self.PAD_LEFT + self.DOT / 2, rect.center().y()), self.DOT / 2, self.DOT / 2)
        p.setPen(qcolor(rgb))
        p.drawText(
            QRectF(self.PAD_LEFT + self.DOT + self.GAP, 0, self.width(), self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            self._text,
        )


class PowerButton(QAbstractButton):
    """Işık açıkken ışığın renginde parlayan büyük yuvarlak güç düğmesi."""

    SIZE = 200

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._accent: RGB = (96, 104, 122)
        self._glow = 0.0
        self._target = 0.0
        self._hover = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_glow)

    # -- durum ---------------------------------------------------------------

    def set_state(self, on: bool, accent: RGB) -> None:
        self._accent = accent
        target = 1.0 if on else 0.0
        if target != self._target:
            self._target = target
            self._anim.stop()
            self._anim.setStartValue(float(self._glow))
            self._anim.setEndValue(target)
            self._anim.start()
        self.update()

    def settle(self) -> None:
        """Animasyonu bitirir (testler ve ekran görüntüleri için)."""
        self._anim.stop()
        self._glow = self._target
        self.update()

    def _on_glow(self, value: object) -> None:
        self._glow = float(value)  # type: ignore[arg-type]
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # -- çizim ---------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        radius = 66.0 * (0.965 if self.isDown() else 1.0)
        glow = self._glow
        accent = self._accent

        if glow > 0.01:  # dış ışıma
            halo = QRadialGradient(c, 100)
            halo.setColorAt(0.55, qcolor(accent, 0.50 * glow))
            halo.setColorAt(0.80, qcolor(accent, 0.14 * glow))
            halo.setColorAt(1.0, qcolor(accent, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, 100, 100)

        body = QLinearGradient(c.x(), c.y() - radius, c.x(), c.y() + radius)
        body.setColorAt(0.0, QColor("#262b37"))
        body.setColorAt(1.0, QColor("#161a22"))
        ring_idle = QColor("#323948")
        ring_on = qcolor(shade(accent, 1.05), 1.0)
        ring = QColor(
            round(ring_idle.red() + (ring_on.red() - ring_idle.red()) * glow),
            round(ring_idle.green() + (ring_on.green() - ring_idle.green()) * glow),
            round(ring_idle.blue() + (ring_on.blue() - ring_idle.blue()) * glow),
        )
        if self._hover and glow < 0.5:
            ring = ring.lighter(135)
        p.setBrush(body)
        p.setPen(QPen(ring, 3.0))
        p.drawEllipse(c, radius, radius)

        icon_on = qcolor(shade(accent, 1.15))
        icon_off = QColor("#7d869a")
        icon = QColor(
            round(icon_off.red() + (icon_on.red() - icon_off.red()) * glow),
            round(icon_off.green() + (icon_on.green() - icon_off.green()) * glow),
            round(icon_off.blue() + (icon_on.blue() - icon_off.blue()) * glow),
        )
        pen = QPen(icon, 6.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc_radius = 27.0
        p.drawArc(QRectF(c.x() - arc_radius, c.y() - arc_radius, arc_radius * 2, arc_radius * 2), 130 * 16, 280 * 16)
        p.drawLine(QPointF(c.x(), c.y() - 33), QPointF(c.x(), c.y() - 8))

        if self.hasFocus():
            p.setPen(QPen(QColor(255, 255, 255, 90), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(c, radius + 8, radius + 8)


class GradientSlider(QSlider):
    """Yuvarlak tutamaçlı, isteğe bağlı gradyan zeminli yatay kaydırıcı."""

    def __init__(self, stops: list[tuple[float, RGB]] | None = None, fill: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._stops: list[tuple[float, RGB]] = stops or [(0.0, (60, 66, 80)), (1.0, (255, 255, 255))]
        self._fill = fill
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_stops(self, stops: list[tuple[float, RGB]]) -> None:
        self._stops = stops
        self.update()

    # -- geometri ------------------------------------------------------------

    def _groove(self) -> QRectF:
        height = 10.0
        return QRectF(14, self.height() / 2 - height / 2, self.width() - 28, height)

    def _fraction(self) -> float:
        span = self.maximum() - self.minimum()
        return 0.0 if span <= 0 else (self.value() - self.minimum()) / span

    def _value_at(self, x: float) -> int:
        groove = self._groove()
        frac = max(0.0, min(1.0, (x - groove.left()) / groove.width()))
        return round(self.minimum() + frac * (self.maximum() - self.minimum()))

    def _color_at(self, frac: float) -> RGB:
        stops = sorted(self._stops)
        if frac <= stops[0][0]:
            return stops[0][1]
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if frac <= p1:
                t = 0.0 if p1 == p0 else (frac - p0) / (p1 - p0)
                return (
                    round(c0[0] + (c1[0] - c0[0]) * t),
                    round(c0[1] + (c1[1] - c0[1]) * t),
                    round(c0[2] + (c1[2] - c0[2]) * t),
                )
        return stops[-1][1]

    # -- fare ----------------------------------------------------------------

    def _set_from_x(self, x: float) -> None:
        value = self._value_at(x)
        if value != self.value():
            self.setValue(value)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self._set_from_x(event.position().x())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self.isSliderDown():
            self._set_from_x(event.position().x())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- çizim ---------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        groove = self._groove()
        radius = groove.height() / 2
        frac = self._fraction()
        x = groove.left() + frac * groove.width()
        gradient = QLinearGradient(groove.left(), 0, groove.right(), 0)
        for pos, rgb in self._stops:
            gradient.setColorAt(pos, qcolor(rgb))

        p.setPen(Qt.PenStyle.NoPen)
        if self._fill:
            p.setBrush(QColor("#232835"))
            p.drawRoundedRect(groove, radius, radius)
            p.save()
            p.setClipRect(QRectF(groove.left(), groove.top() - 2, max(x - groove.left(), 0), groove.height() + 4))
            p.setBrush(gradient)
            p.drawRoundedRect(groove, radius, radius)
            p.restore()
        else:
            p.setBrush(gradient)
            p.drawRoundedRect(groove, radius, radius)

        cy = groove.center().y()
        p.setBrush(QColor(0, 0, 0, 80))
        p.drawEllipse(QPointF(x, cy + 1.5), 13.5, 13.5)
        p.setBrush(QColor("#f4f6fb"))
        p.drawEllipse(QPointF(x, cy), 12, 12)
        p.setBrush(qcolor(self._color_at(frac)))
        p.drawEllipse(QPointF(x, cy), 6.5, 6.5)


class ColorWheel(QWidget):
    """Renk tonu (çevre) ve doygunluk (merkezden uzaklık) seçen çark."""

    changed = Signal(int, int)  # H 0-360, S 0-1000 (sürüklenirken)
    released = Signal(int, int)  # fare bırakıldığında

    def __init__(self, size: int = 220, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._hue = 30
        self._sat = 800
        self._dragging = False
        self._cache: QPixmap | None = None

    def hs(self) -> tuple[int, int]:
        return self._hue, self._sat

    def set_hs(self, hue: int, sat: int) -> None:
        hue = max(0, min(360, int(hue)))
        sat = max(0, min(1000, int(sat)))
        if (hue, sat) != (self._hue, self._sat):
            self._hue, self._sat = hue, sat
            self.update()

    # -- geometri ------------------------------------------------------------

    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _radius(self) -> float:
        return self.width() / 2 - 16

    def _update_from(self, pos: QPointF) -> None:
        c = self._center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        hue = round(math.degrees(math.atan2(-dy, dx)) % 360)
        sat = round(min(math.hypot(dx, dy) / self._radius(), 1.0) * 1000)
        self._hue, self._sat = hue, sat
        self.update()
        self.changed.emit(hue, sat)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            c = self._center()
            pos = event.position()
            if math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= self._radius() + 14:
                self._dragging = True
                self._update_from(pos)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._update_from(event.position())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.released.emit(self._hue, self._sat)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # -- çizim ---------------------------------------------------------------

    def _wheel(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        if self._cache is not None and self._cache.devicePixelRatio() == dpr:
            return self._cache
        pm = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c, r = self._center(), self._radius()
        hue = QConicalGradient(c, 0)
        for i in range(13):
            t = i / 12
            hue.setColorAt(t, QColor.fromHsvF(min(t, 0.9999), 1.0, 1.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(hue)
        p.drawEllipse(c, r, r)
        sat = QRadialGradient(c, r)
        sat.setColorAt(0.0, QColor(255, 255, 255, 255))
        sat.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(sat)
        p.drawEllipse(c, r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 36), 1.5))
        p.drawEllipse(c, r, r)
        p.end()
        self._cache = pm
        return pm

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._wheel())
        c, r = self._center(), self._radius()
        angle = math.radians(self._hue)
        dist = self._sat / 1000 * r
        marker = QPointF(c.x() + dist * math.cos(angle), c.y() - dist * math.sin(angle))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(QPointF(marker.x(), marker.y() + 1.5), 13, 13)
        p.setBrush(QColor("#f4f6fb"))
        p.drawEllipse(marker, 12, 12)
        p.setBrush(qcolor(hs_rgb(self._hue, self._sat)))
        p.drawEllipse(marker, 8, 8)
