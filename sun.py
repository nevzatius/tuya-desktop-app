"""Gün doğumu / gün batımı hesabı: internetsiz, saf Python (NOAA güneş hesabı formülleri).

Enlem kuzey +, boylam doğu + (derece). Doğruluk genellikle bir dakikanın altındadır; atmosfer kırılması
(güneşin üst kenarı ufukta, zenit 90,833°) hesaba katılır. Kutup bölgelerinde güneş hiç doğmayabilir ya da
batmayabilir: bu durumda `None` döner.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

ZENITH = 90.833  # güneşin merkezi ufkun 0,833° altındayken doğuş/batış (kırılma + yarıçap)
_EPOCH_JD = 2440587.5  # 1970-01-01 00:00 UTC


def _julian_day(ts: float) -> float:
    return ts / 86400.0 + _EPOCH_JD


def _equation_of_time_and_declination(jd: float) -> tuple[float, float]:
    """(zaman denklemi dakika, güneşin dikliği derece) — verilen Jülyen gün için."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    rad_m = math.radians(m)
    c = (
        math.sin(rad_m) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * rad_m) * (0.019993 - 0.000101 * t)
        + math.sin(3 * rad_m) * 0.000289
    )
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    apparent_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    mean_obliquity = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    obliquity = mean_obliquity + 0.00256 * math.cos(math.radians(omega))
    declination = math.degrees(math.asin(math.sin(math.radians(obliquity)) * math.sin(math.radians(apparent_long))))
    y = math.tan(math.radians(obliquity / 2.0)) ** 2
    rad_l0 = math.radians(l0)
    equation = 4.0 * math.degrees(
        y * math.sin(2 * rad_l0)
        - 2.0 * e * math.sin(rad_m)
        + 4.0 * e * y * math.sin(rad_m) * math.cos(2 * rad_l0)
        - 0.5 * y * y * math.sin(4 * rad_l0)
        - 1.25 * e * e * math.sin(2 * rad_m)
    )
    return equation, declination


def _hour_angle(lat: float, declination: float) -> float | None:
    """Doğuş saat açısı (derece, pozitif); güneş o gün doğmuyor/batmıyorsa None."""
    rad_lat, rad_dec = math.radians(lat), math.radians(declination)
    cos_ha = math.cos(math.radians(ZENITH)) / (math.cos(rad_lat) * math.cos(rad_dec)) - math.tan(rad_lat) * math.tan(rad_dec)
    if cos_ha < -1.0 or cos_ha > 1.0:
        return None
    return math.degrees(math.acos(cos_ha))


def sun_event_ts(utc_day: date, lat: float, lon: float, event: str) -> float | None:
    """`utc_day` (UTC takvim günü) için gün doğumu ya da batımının UTC epoch saniyesi.

    `event`: "sunrise" | "sunset". Sonuç, o UTC gününün sınırları dışına taşabilir (doğuya/batıya uzak yerlerde);
    hangi yerel güne ait olduğunu çağıran belirler. Kutupta güneş doğmuyor/batmıyorsa None.
    """
    if event not in ("sunrise", "sunset"):
        raise ValueError(f"unknown sun event: {event!r}")
    midnight = datetime(utc_day.year, utc_day.month, utc_day.day, tzinfo=timezone.utc).timestamp()
    minutes = 720.0 - 4.0 * lon  # ilk tahmin: öğle
    for _ in range(3):  # olay anındaki güneş konumuyla yeniden hesapla
        equation, declination = _equation_of_time_and_declination(_julian_day(midnight + minutes * 60.0))
        ha = _hour_angle(lat, declination)
        if ha is None:
            return None
        delta = lon + ha if event == "sunrise" else lon - ha
        minutes = 720.0 - 4.0 * delta - equation
    return midnight + minutes * 60.0
