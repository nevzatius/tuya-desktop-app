from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import energy as en  # noqa: E402
import light_core as lc  # noqa: E402


def ts(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi).timestamp()


def st(**kw):
    return lc.LightState(**kw)


# -- güç tahmini -------------------------------------------------------------------


def test_estimate_watts_cases():
    assert en.estimate_watts(st(power=False, brightness_pct=100), 10) == 0
    assert en.estimate_watts(st(), 10) == 0  # durum bilinmiyor
    assert en.estimate_watts(st(power=True, mode="white", brightness_pct=50), 10) == pytest.approx(5)
    assert en.estimate_watts(st(power=True, mode="white", brightness_pct=1), 10) == pytest.approx(0.5)  # taban %5
    assert en.estimate_watts(st(power=True, mode="colour", val=500, brightness_pct=99), 10) == pytest.approx(5)
    assert en.estimate_watts(st(power=True), 10) == 10  # parlaklık bilinmiyor: tam güç
    assert en.estimate_watts(st(power=True, brightness_pct=100), 0) == 0


def test_kwh_math():
    assert en.kwh(1000, 3600) == pytest.approx(1.0)
    assert en.kwh(9, 3600 * 10) == pytest.approx(0.09)


# -- kayıt -------------------------------------------------------------------------


@pytest.fixture()
def log():
    clock = {"t": ts(2026, 10, 27, 12)}
    lg = en.EnergyLog(":memory:", clock=lambda: clock["t"])
    lg.clock = clock
    return lg


def test_segment_lifecycle_and_total(log):
    t0 = ts(2026, 10, 27, 12)
    log.set_watts("a", 10, t0)
    assert log.is_open("a")
    log.set_watts("a", 10, t0 + 1800)  # aynı güç: aralık uzar
    log.set_watts("a", 5, t0 + 3600)  # parlaklık değişti: yeni aralık
    log.stop("a", t0 + 7200)
    assert not log.is_open("a")
    kwh, secs = log.total(t0, t0 + 86400, "a")
    assert kwh == pytest.approx(0.010 + 0.005) and secs == 7200


def test_zero_watts_never_opens_segment(log):
    log.set_watts("a", 0, ts(2026, 10, 27, 12))
    assert not log.is_open("a") and log.total(0, 4e9)[1] == 0


def test_heartbeat_extends_open_segment_and_survives_restart(tmp_path):
    path = tmp_path / "e.db"
    t0 = ts(2026, 10, 27, 12)
    lg = en.EnergyLog(path)
    lg.set_watts("a", 10, t0)
    lg.heartbeat(t0 + 600)
    lg._db.close()  # çökme: kapatma çağrılmadı
    lg2 = en.EnergyLog(path)
    kwh, secs = lg2.total(t0, t0 + 86400, "a")
    assert secs == 600 and kwh == pytest.approx(10 * 600 / 3.6e6)
    assert not lg2.is_open("a")  # eski açık aralık yeniden açılmaz


def test_total_clips_to_range_and_filters_device(log):
    t0 = ts(2026, 10, 27, 10)
    log.set_watts("a", 10, t0)
    log.stop("a", t0 + 7200)
    log.set_watts("b", 20, t0)
    log.stop("b", t0 + 3600)
    assert log.total(t0 + 3600, t0 + 7200, "a")[1] == 3600  # yalnızca kesişen saat
    assert log.total(t0, t0 + 7200, "b")[1] == 3600
    both, _ = log.total(t0, t0 + 7200)
    assert both == pytest.approx(0.020 + 0.020)  # a: 10W*2h, b: 20W*1h
    assert log.total(t0 + 9000, t0 + 9100)[1] == 0


def test_close_all(log):
    log.set_watts("a", 5, 1000.0)
    log.set_watts("b", 5, 1000.0)
    log.close_all(2000.0)
    assert not log.is_open("a") and not log.is_open("b")


# -- dönemler ----------------------------------------------------------------------


def test_day_buckets_split_midnight_crossing_segment(log):
    # 23:00 - 01:00 arası 10 W: bugün 1 saat, yarın 1 saat
    log.set_watts("a", 10, ts(2026, 10, 26, 23))
    log.stop("a", ts(2026, 10, 27, 1))
    now = ts(2026, 10, 27, 12)
    day = en.summarize(log, "day", 4.0, "a", now)
    assert len(day.buckets) == 24 and day.buckets[0].label == "00"
    assert day.buckets[0].kwh == pytest.approx(0.010) and day.buckets[1].kwh == 0
    assert day.kwh == pytest.approx(0.010) and day.seconds == 3600
    week = en.summarize(log, "week", 4.0, "a", now)
    assert len(week.buckets) == 7 and week.kwh == pytest.approx(0.020)
    assert week.buckets[-1].kwh == pytest.approx(0.010) and week.buckets[-2].kwh == pytest.approx(0.010)


def test_week_and_month_labels_and_lengths(log):
    now = ts(2026, 10, 27, 12)  # Salı
    week = en.summarize(log, "week", 1, None, now)
    assert [b.label for b in week.buckets] == ["Çar", "Per", "Cum", "Cmt", "Paz", "Pzt", "Sal"]
    month = en.summarize(log, "month", 1, None, now)
    assert len(month.buckets) == 30 and month.buckets[-1].label == "27" and month.buckets[0].label == "28"


def test_cost_uses_price(log):
    log.set_watts("a", 1000, ts(2026, 10, 27, 8))
    log.stop("a", ts(2026, 10, 27, 10))
    s = en.summarize(log, "day", 3.37, "a", ts(2026, 10, 27, 12))
    assert s.kwh == pytest.approx(2.0) and s.cost_tl == pytest.approx(6.74)


def test_all_devices_summary(log):
    log.set_watts("a", 10, ts(2026, 10, 27, 8))
    log.stop("a", ts(2026, 10, 27, 9))
    log.set_watts("b", 10, ts(2026, 10, 27, 8))
    log.stop("b", ts(2026, 10, 27, 9))
    now = ts(2026, 10, 27, 12)
    assert en.summarize(log, "day", 1, None, now).kwh == pytest.approx(0.020)
    assert en.summarize(log, "day", 1, "a", now).kwh == pytest.approx(0.010)


def test_dst_free_day_edges_cover_whole_day(log):
    start, end, edges = en.period_edges("day", ts(2026, 10, 27, 15))
    assert edges[0][1] == start and edges[-1][2] == end and end - start == 86400


# -- biçimlendirme -------------------------------------------------------------------


def test_formatting():
    assert en.fmt_tl(1234.5) == "₺1.234,50" and en.fmt_tl(0) == "₺0,00"
    assert en.fmt_kwh(0.0456) == "0,046 kWh" and en.fmt_kwh(12.5) == "12,50 kWh"
    assert en.fmt_duration(0) == "0 dk" and en.fmt_duration(3600) == "1 sa" and en.fmt_duration(5400) == "1 sa 30 dk"


# -- izleyici ---------------------------------------------------------------------------


def test_tracker_follows_state_connection_and_device_switch(log):
    tr = en.UsageTracker(log)
    tr.set_device("a", 10)
    log.clock["t"] = ts(2026, 10, 27, 12)
    tr.on_state(st(power=True, mode="white", brightness_pct=100))
    assert log.is_open("a")
    tr.on_state(st(power=False))
    assert not log.is_open("a")
    tr.on_state(st(power=True, brightness_pct=50))
    tr.on_connected(False)  # bağlantı koptu: durum bilinmiyor
    assert not log.is_open("a")
    tr.on_state(st(power=True, brightness_pct=50))
    tr.set_device("b", 20)  # ışık değişti: eskisi kapanır
    assert not log.is_open("a")
    tr.on_state(st(power=True, brightness_pct=100))
    assert log.is_open("b")
    tr.release()
    assert not log.is_open("b") and tr.device == ""
    tr.on_state(st(power=True))  # cihaz yok: kayıt açılmaz
    assert not log.is_open("b")


def test_config_watts_roundtrip_and_validation(tmp_path):
    c = lc.Config(device_id="d", local_key="k" * 16, uuid="u", watts=12.5)
    path = tmp_path / "c.json"
    c.save(path)
    assert lc.Config.load(path).watts == 12.5
    assert lc._watts("abc") == 9.0 and lc._watts(-3) == 9.0 and lc._watts(99999) == 9.0 and lc._watts(None) == 9.0
