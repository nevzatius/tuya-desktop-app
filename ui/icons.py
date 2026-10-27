"""Kodla çizilen uygulama simgesi (pencere, tepsi ve .ico için)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient

SIZES = (16, 24, 32, 48, 64, 128, 256)
DEFAULT_ACCENT = (255, 196, 92)


def render_icon(size: int, accent: tuple[int, int, int] = DEFAULT_ACCENT, background: bool = True) -> QPixmap:
    """Ampul simgesini `size` piksel kare olarak çizer (çizim koordinatı 256x256)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)

    if background:
        bg = QLinearGradient(0, 0, 0, 256)
        bg.setColorAt(0, QColor("#222838"))
        bg.setColorAt(1, QColor("#0f1218"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(8, 8, 240, 240), 56, 56)

    accent_color = QColor(*accent)
    halo = QRadialGradient(QPointF(128, 108), 120)
    halo_color = QColor(accent_color)
    halo_color.setAlphaF(0.45)
    halo.setColorAt(0.0, halo_color)
    halo_color.setAlphaF(0.0)
    halo.setColorAt(1.0, halo_color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(halo)
    p.drawEllipse(QPointF(128, 108), 120, 120)

    glass = QLinearGradient(0, 56, 0, 170)
    glass.setColorAt(0, accent_color.lighter(125))
    glass.setColorAt(1, accent_color.darker(105))
    p.setBrush(glass)
    p.drawEllipse(QPointF(128, 108), 56, 56)
    p.drawRoundedRect(QRectF(104, 140, 48, 34), 12, 12)

    p.setBrush(QColor("#8d96aa"))
    p.drawRoundedRect(QRectF(104, 178, 48, 13), 6.5, 6.5)
    p.drawRoundedRect(QRectF(114, 194, 28, 11), 5.5, 5.5)

    shine = QPen(QColor(255, 255, 255, 150), 8)
    shine.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(shine)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(92, 72, 44, 44), 100 * 16, 70 * 16)
    p.end()
    return pm


def app_icon(accent: tuple[int, int, int] = DEFAULT_ACCENT) -> QIcon:
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(render_icon(size, accent))
    return icon
