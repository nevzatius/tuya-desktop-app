"""Gün doğumu/batımı hesabı: bilinen konum ve tarihler için yayımlanmış saatlerle ±3 dakika.

Beklenen değerler yerel saattir ve ayrıca bağımsız bir güneş kütüphanesiyle (astral) çapraz kontrol edilmiştir.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

import sun

TOLERANCE_MIN = 3


def local_time(ts: float, hours: float) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc) + timedelta(hours=hours)


def minutes_between(got: datetime, hour: int, minute: int) -> float:
    expected = got.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return abs((got - expected).total_seconds()) / 60


def event_on(day: date, lat: float, lon: float, event: str, utc_hours: float) -> datetime | None:
    """Yerel `day` gününe düşen olayı bulur (UTC günü yerel günden farklı olabilir)."""
    for shift in (0, -1, 1):
        ts = sun.sun_event_ts(day + timedelta(days=shift), lat, lon, event)
        if ts is not None and local_time(ts, utc_hours).date() == day:
            return local_time(ts, utc_hours)
    return None


@pytest.mark.parametrize(
    ("place", "lat", "lon", "utc_hours", "day", "rise", "set_"),
    [
        ("London, yaz gündönümü (BST)", 51.5074, -0.1278, 1, date(2026, 6, 21), (4, 43), (21, 21)),
        ("London, kış gündönümü (GMT)", 51.5074, -0.1278, 0, date(2026, 12, 21), (8, 4), (15, 53)),
        ("New York, yaz gündönümü (EDT)", 40.7128, -74.0060, -4, date(2026, 6, 21), (5, 25), (20, 31)),
        ("İstanbul, yaz gündönümü (+03)", 41.0082, 28.9784, 3, date(2026, 6, 21), (5, 32), (20, 39)),
        ("İstanbul, ilkbahar ekinoksu (+03)", 41.0082, 28.9784, 3, date(2026, 3, 20), (7, 8), (19, 15)),
        ("Quito, ekvator (-05)", -0.18, -78.47, -5, date(2026, 3, 20), (6, 18), (18, 24)),
        ("Sydney, yaz (+11, doğu yarımküre/güney)", -33.8688, 151.2093, 11, date(2026, 12, 21), (5, 41), (20, 5)),
    ],
)
def test_known_places_and_dates(place, lat, lon, utc_hours, day, rise, set_):
    sunrise = event_on(day, lat, lon, "sunrise", utc_hours)
    sunset = event_on(day, lat, lon, "sunset", utc_hours)
    assert sunrise is not None and sunset is not None, place
    assert minutes_between(sunrise, *rise) <= TOLERANCE_MIN, (place, sunrise)
    assert minutes_between(sunset, *set_) <= TOLERANCE_MIN, (place, sunset)
    assert sunrise < sunset


def test_midnight_sun_and_polar_night_return_none():
    tromso = (69.6496, 18.9560)
    assert sun.sun_event_ts(date(2026, 6, 21), *tromso, "sunrise") is None  # gece yarısı güneşi
    assert sun.sun_event_ts(date(2026, 6, 21), *tromso, "sunset") is None
    assert sun.sun_event_ts(date(2026, 12, 21), *tromso, "sunrise") is None  # kutup gecesi
    assert sun.sun_event_ts(date(2026, 12, 21), *tromso, "sunset") is None
    assert sun.sun_event_ts(date(2026, 3, 20), *tromso, "sunrise") is not None  # ekinokta normal


def test_days_get_longer_towards_summer_in_the_north():
    def day_length(day: date) -> float:
        rise = sun.sun_event_ts(day, 41.0, 29.0, "sunrise")
        set_ = sun.sun_event_ts(day, 41.0, 29.0, "sunset")
        return set_ - rise

    assert day_length(date(2026, 12, 21)) < day_length(date(2026, 3, 20)) < day_length(date(2026, 6, 21))
    assert abs(day_length(date(2026, 3, 20)) - 12 * 3600) < 20 * 60  # ekinokta yaklaşık 12 saat


def test_unknown_event_is_rejected():
    with pytest.raises(ValueError):
        sun.sun_event_ts(date(2026, 6, 21), 41.0, 29.0, "noon")
