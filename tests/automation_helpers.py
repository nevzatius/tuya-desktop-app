"""Otomasyon testleri için ortak yardımcılar: sahte saat dilimleri, sahte arka uç, sahte zaman."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import automation as au
import light_core as lc

UTC = timezone.utc


def _as_epoch(naive: datetime) -> float:
    return naive.replace(tzinfo=UTC).timestamp()


class FixedZone:
    """Yaz saati olmayan sabit UTC farkı (ör. Türkiye = +3)."""

    def __init__(self, hours: float = 3) -> None:
        self.seconds = int(hours * 3600)

    def local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts + self.seconds, UTC).replace(tzinfo=None)

    def instant(self, naive: datetime) -> float:
        return _as_epoch(naive) - self.seconds


class DstZone:
    """Avrupa tarzı yaz saati (2026): 29 Mart 02:00 -> 03:00 (ileri), 25 Ekim 03:00 -> 02:00 (geri). Kış +1, yaz +2.

    Belirsiz yerel saatte (sonbahar) ilk, olmayan yerel saatte (ilkbahar) geçiş öncesi farkla çözer (PEP 495, fold=0).
    """

    SPRING = datetime(2026, 3, 29, 1, tzinfo=UTC).timestamp()
    AUTUMN = datetime(2026, 10, 25, 1, tzinfo=UTC).timestamp()

    def offset(self, ts: float) -> int:
        return 7200 if self.SPRING <= ts < self.AUTUMN else 3600

    def local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts + self.offset(ts), UTC).replace(tzinfo=None)

    def instant(self, naive: datetime) -> float:
        wall = _as_epoch(naive)
        valid = [wall - off for off in (7200, 3600) if self.offset(wall - off) == off]
        if valid:
            return min(valid)  # belirsizse ilk an
        return wall - 3600  # olmayan saat: geçiş öncesi fark -> boşluk kadar ileri kayar


def at(zone, year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> float:
    return zone.instant(datetime(year, month, day, hour, minute, second))


def local_text(zone, ts: float) -> str:
    return zone.local(ts).strftime("%Y-%m-%d %H:%M")


def make_rule(
    name: str = "Kural",
    trigger: au.Trigger | None = None,
    action: au.Action | None = None,
    lights: list[str] | None = None,
    all_lights: bool = False,
    enabled: bool = True,
) -> au.Rule:
    return au.Rule(
        name=name,
        enabled=enabled,
        trigger=trigger or au.Trigger(kind="time", time="07:00"),
        action=action or au.Action(kind="power", power=True),
        all_lights=all_lights,
        lights=lights if lights is not None else ([] if all_lights else ["light-1"]),
    )


# -- sahte arka uç ---------------------------------------------------------------------------------


@dataclass
class FakeState:
    power: bool | None = True
    mode: str | None = "white"
    brightness_pct: int | None = 50
    temp_pct: int | None = 50
    val: int | None = None


class Sim:
    """Sahte zaman: `sleep` saati ilerletir; gerçek bekleme yok."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.hook = None  # sleep sonrası çağrılır (testin araya girmesi için)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        if self.hook is not None:
            await self.hook(self)

    def clock(self) -> float:
        return self.now


@dataclass
class FakeBackend:
    names: dict[str, str] = field(default_factory=lambda: {"light-1": "Salon"})
    states: dict[str, FakeState] = field(default_factory=dict)
    fail: dict[str, int] = field(default_factory=dict)  # ışık -> kaç çağrı daha hata versin (-1: hep)
    calls: list[tuple[str, au.Command]] = field(default_factory=list)
    released: list[str] = field(default_factory=list)
    state_reads: int = 0
    on_apply: object = None  # (backend, light, command, çağrı sayısı) -> None
    reflect: bool = True  # komutlar sahte ışığın durumunu günceller (gerçek istemcinin iyimser güncellemesi gibi)

    def light_ids(self) -> list[str]:
        return list(self.names)

    def light_name(self, light_id: str) -> str | None:
        return self.names.get(light_id)

    async def state(self, light_id: str):
        self.state_reads += 1
        return self.states.setdefault(light_id, FakeState())

    async def apply(self, light_id: str, command: au.Command) -> None:
        remaining = self.fail.get(light_id, 0)
        if remaining != 0:
            if remaining > 0:
                self.fail[light_id] = remaining - 1
            raise OSError("light unreachable")
        self.calls.append((light_id, command))
        if self.reflect:
            self._reflect(light_id, command)
        if self.on_apply is not None:
            self.on_apply(self, light_id, command, len(self.calls))

    def _reflect(self, light_id: str, command: au.Command) -> None:
        st = self.states.setdefault(light_id, FakeState())
        if command.kind == "power":
            st.power = command.on
        elif command.kind == "brightness":
            st.brightness_pct = command.bright
        elif command.kind == "white":
            st.mode, st.brightness_pct, st.temp_pct = "white", command.bright, command.temp
        elif command.kind == "colour":
            st.mode, st.val = "colour", lc.pct_to_bright(command.bright)
        elif command.kind == "scene":
            st.power, st.mode = True, command.mode
            if command.mode == "white":
                st.brightness_pct, st.temp_pct = command.bright, command.temp
            else:
                st.val = lc.pct_to_bright(command.bright)

    async def release(self, light_id: str) -> None:
        self.released.append(light_id)

    # kolaylık
    def commands(self, light_id: str | None = None) -> list[au.Command]:
        return [c for light, c in self.calls if light_id is None or light == light_id]


@dataclass
class Preset:
    mode: str
    bright: int
    temp: int = 0
    hue: int = 0
    sat: int = 0
