"""Renk hesapları (Qt'den bağımsız, düz RGB demetleri)."""

from __future__ import annotations

import colorsys

RGB = tuple[int, int, int]

WARM: RGB = (255, 164, 72)
NEUTRAL: RGB = (255, 241, 224)
COOL: RGB = (186, 214, 255)
OFF: RGB = (96, 104, 122)


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def white_rgb(temp_pct: float) -> RGB:
    """Beyaz ışık sıcaklığı (0 sıcak … 100 soğuk) için yaklaşık görünen renk."""
    t = max(0.0, min(100.0, temp_pct)) / 100
    if t <= 0.5:
        return _lerp(WARM, NEUTRAL, t / 0.5)
    return _lerp(NEUTRAL, COOL, (t - 0.5) / 0.5)


def hs_rgb(hue: float, sat: float, value: float = 1.0) -> RGB:
    """Cihazın birimleriyle (H 0-360, S 0-1000) renk; V 0-1."""
    r, g, b = colorsys.hsv_to_rgb((hue % 360) / 360, max(0, min(1000, sat)) / 1000, max(0.0, min(1.0, value)))
    return round(r * 255), round(g * 255), round(b * 255)


def accent_for(
    power: bool | None,
    mode: str | None,
    temp_pct: float | None,
    hue: float | None,
    sat: float | None,
) -> RGB:
    """Arayüzün vurgu rengi: ışık kapalıysa gri, açıksa ışığın gerçek rengi."""
    if power is not True:
        return OFF
    if mode == "colour" and hue is not None and sat is not None:
        # Çok soluk renklerde vurgu görünmez olmasın.
        return hs_rgb(hue, max(sat, 350))
    return white_rgb(temp_pct if temp_pct is not None else 0)


def shade(rgb: RGB, factor: float) -> RGB:
    """factor < 1 karartır, > 1 açar."""
    if factor <= 1:
        return (round(rgb[0] * factor), round(rgb[1] * factor), round(rgb[2] * factor))
    return _lerp(rgb, (255, 255, 255), factor - 1)


def hex_of(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)
