"""Enerji tüketimi tahmini (arayüzden bağımsız).

Işık anlık güç ölçmez. Tahmin: ışığın tam parlaklıktaki gücü (watt) × parlaklık oranı × açık kalma süresi.
Süre yalnızca uygulama çalışırken ve ışığa bağlıyken kaydedilir; bağlantı yokken ya da uygulama kapalıyken
ışık yanıyor olsa bile sayılmaz. Bu yüzden değerler gerçek faturanın alt sınırına yakın bir **tahmindir**.

Kayıtlar `energy.db` (SQLite) içinde "aralık"lar olarak tutulur: (cihaz, başlangıç, bitiş, watt).
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import light_core as lc

# EPDK mesken tarifesi, 4 Nisan 2026, kademe 1 (aylık 240 kWh'e kadar): 2,92 TL/kWh (KDV/BTV hariç).
# KDV %10 ve BTV %5 ile ≈ 3,37 TL/kWh. Tarifeler her çeyrekte değişebilir: kullanıcı kendi faturasındaki değeri girer.
DEFAULT_PRICE_TL = 3.37
PRICE_NOTE = "EPDK mesken tarifesi (Nisan 2026, kademe 1, KDV ve BTV dahil) ≈ 3,37 TL/kWh. Güncel fiyat için faturanıza bakın."
MIN_FRACTION = 0.05  # LED sürücüsü kısık parlaklıkta bile bir miktar çeker
EPSILON_W = 0.05


def estimate_watts(state: lc.LightState, rated_watts: float) -> float:
    """Durumdan anlık güç tahmini (W). Kapalı ya da bilinmiyorsa 0."""
    if state.power is not True or rated_watts <= 0:
        return 0.0
    if state.mode == "colour" and state.val is not None:
        fraction = state.val / 1000
    elif state.brightness_pct is not None:
        fraction = state.brightness_pct / 100
    else:
        fraction = 1.0  # parlaklık bilinmiyor: tam güç varsay (üst tahmin)
    return rated_watts * min(1.0, max(MIN_FRACTION, fraction))


def kwh(watts: float, seconds: float) -> float:
    return watts * seconds / 3_600_000


@dataclass
class Bucket:
    label: str  # eksen etiketi ("14", "Pzt", "27")
    start: float
    end: float
    kwh: float = 0.0
    seconds: float = 0.0


class EnergyLog:
    def __init__(self, path: Path | str | None = None, clock: Callable[[], float] = time.time) -> None:
        if path is None:
            import devices

            path = devices.user_data_dir() / "energy.db"
        self.path = Path(path)
        self._clock = clock
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS segments (id INTEGER PRIMARY KEY, device TEXT NOT NULL, "
            "start REAL NOT NULL, end REAL NOT NULL, watts REAL NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS seg_time ON segments(start, end)")
        self._db.commit()
        self._open: dict[str, tuple[int, float]] = {}  # cihaz -> (satır id, watt)

    def close(self) -> None:
        self.close_all()
        self._db.close()

    # -- kayıt ---------------------------------------------------------------

    def set_watts(self, device: str, watts: float, now: float | None = None) -> None:
        """Işığın güç tahmini değişti (0 = kapalı). Gerekirse aralığı kapatıp yenisini açar."""
        now = self._clock() if now is None else now
        current = self._open.get(device)
        if current is not None:
            row, old = current
            if abs(old - watts) < EPSILON_W:
                self._db.execute("UPDATE segments SET end=? WHERE id=?", (now, row))
                self._db.commit()
                return
            self._db.execute("UPDATE segments SET end=? WHERE id=?", (now, row))
            del self._open[device]
        if watts >= EPSILON_W:
            cur = self._db.execute(
                "INSERT INTO segments(device, start, end, watts) VALUES (?,?,?,?)", (device, now, now, watts)
            )
            self._open[device] = (cur.lastrowid, watts)
        self._db.commit()

    def heartbeat(self, now: float | None = None) -> None:
        """Açık aralıkların bitişini ilerletir (çökme olursa en fazla bir vuruş kaybolur)."""
        now = self._clock() if now is None else now
        for row, _ in self._open.values():
            self._db.execute("UPDATE segments SET end=? WHERE id=?", (now, row))
        self._db.commit()

    def stop(self, device: str, now: float | None = None) -> None:
        self.set_watts(device, 0.0, now)

    def close_all(self, now: float | None = None) -> None:
        for device in list(self._open):
            self.stop(device, now)

    def is_open(self, device: str) -> bool:
        return device in self._open

    # -- sorgu ---------------------------------------------------------------

    def _segments(self, start: float, end: float, device: str | None) -> list[tuple[float, float, float]]:
        sql = "SELECT start, end, watts FROM segments WHERE end > ? AND start < ?"
        args: list = [start, end]
        if device is not None:
            sql += " AND device = ?"
            args.append(device)
        return self._db.execute(sql, args).fetchall()

    def total(self, start: float, end: float, device: str | None = None) -> tuple[float, float]:
        """(kWh, saniye) — [start, end) aralığına düşen kısım."""
        total_kwh = total_s = 0.0
        for s, e, w in self._segments(start, end, device):
            overlap = min(e, end) - max(s, start)
            if overlap > 0:
                total_kwh += kwh(w, overlap)
                total_s += overlap
        return total_kwh, total_s

    def buckets(self, edges: list[tuple[str, float, float]], device: str | None = None) -> list[Bucket]:
        out = [Bucket(label, a, b) for label, a, b in edges]
        if not out:
            return out
        for s, e, w in self._segments(out[0].start, out[-1].end, device):
            for bucket in out:
                overlap = min(e, bucket.end) - max(s, bucket.start)
                if overlap > 0:
                    bucket.kwh += kwh(w, overlap)
                    bucket.seconds += overlap
        return out


# -- dönemler (yerel saate göre) -------------------------------------------------

TR_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
PERIODS = ("day", "week", "month")


def _midnight(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def period_edges(period: str, now: float) -> tuple[float, float, list[tuple[str, float, float]]]:
    """(dönem başı, dönem sonu, çubuk aralıkları). gün: bugünün 24 saati; hafta: son 7 gün; ay: son 30 gün."""
    today = _midnight(datetime.fromtimestamp(now))
    if period == "day":
        edges = [(f"{h:02d}", (today + timedelta(hours=h)).timestamp(), (today + timedelta(hours=h + 1)).timestamp()) for h in range(24)]
        return today.timestamp(), (today + timedelta(days=1)).timestamp(), edges
    days = 7 if period == "week" else 30
    first = today - timedelta(days=days - 1)
    edges = []
    for i in range(days):
        day = first + timedelta(days=i)
        label = TR_DAYS[day.weekday()] if days == 7 else str(day.day)
        edges.append((label, day.timestamp(), (day + timedelta(days=1)).timestamp()))
    return first.timestamp(), (today + timedelta(days=1)).timestamp(), edges


@dataclass
class Summary:
    kwh: float
    seconds: float
    cost_tl: float
    buckets: list[Bucket]
    start: float
    end: float


def summarize(log: EnergyLog, period: str, price_tl: float, device: str | None = None, now: float | None = None) -> Summary:
    now = log._clock() if now is None else now
    start, end, edges = period_edges(period, now)
    buckets = log.buckets(edges, device)
    total_kwh = sum(b.kwh for b in buckets)
    seconds = sum(b.seconds for b in buckets)
    return Summary(total_kwh, seconds, total_kwh * price_tl, buckets, start, end)


# -- biçimlendirme (Türkçe) ----------------------------------------------------------


def fmt_tl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"₺{text}"


def fmt_kwh(value: float) -> str:
    digits = 3 if value < 1 else 2
    return f"{value:.{digits}f}".replace(".", ",") + " kWh"


def fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} sa {minutes} dk"
    if hours:
        return f"{hours} sa"
    return f"{minutes} dk"


class UsageTracker:
    """Işık durum bildirimlerini enerji kaydına çevirir."""

    def __init__(self, log: EnergyLog) -> None:
        self.log = log
        self.device = ""
        self.watts = 9.0  # seçili ışığın nominal gücü

    def set_device(self, device: str, watts: float) -> None:
        if device != self.device:
            if self.device:
                self.log.stop(self.device)
            self.device = device
        self.watts = watts

    def on_state(self, state: lc.LightState) -> None:
        if self.device:
            self.log.set_watts(self.device, estimate_watts(state, self.watts))

    def on_connected(self, ok: bool) -> None:
        if not ok and self.device:  # durum bilinmiyor: sayma
            self.log.stop(self.device)

    def heartbeat(self) -> None:
        self.log.heartbeat()

    def release(self) -> None:
        if self.device:
            self.log.stop(self.device)
            self.device = ""
