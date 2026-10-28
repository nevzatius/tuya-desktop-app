"""Otomasyon motoru (Qt'den bağımsız): kurallar, zamanlayıcı, yumuşak geçiş ve çalıştırıcı.

Parçalar:

* `Rule` / `Trigger` / `Action`: kural modeli ve doğrulama. `RuleStore`: `automations.json`.
* `Scheduler`: saat verilince hangi kuralların çalışacağını söyler (saat dışarıdan verilir; testte sahte saat).
  Aynı kural aynı gün/dakikada iki kez çalışmaz; kaçırılan kural tolerans süresi içinde bir kez çalışır.
* `fade_plan`: yumuşak geçişin adımları. `Runner`: kuralı ışıklara uygular (yeniden deneme, geçiş, elle müdahale).
* `Backend`: ışıklara gerçekten komut gönderen katman (uygulamada ui/automation_host.py'de; testte sahte).

Otomasyonlar yalnızca uygulama çalışırken, bilgisayar uyanıkken ve ışık Bluetooth menzilindeyken çalışır.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import math
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import storage
import sun
from light_core import bright_to_pct

LOGGER = logging.getLogger("tuya_light.automation")

STORE_VERSION = 1
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)  # 0 = Pazartesi … 6 = Pazar (datetime.weekday)
TRIGGER_KINDS = ("time", "sun", "startup")
ACTION_KINDS = ("power", "brightness", "white", "colour", "preset")
SUN_EVENTS = ("sunrise", "sunset")
MAX_NAME = 40
MAX_RULES = 50
MAX_FADE_MIN = 120
MAX_OFFSET_MIN = 360
DEFAULT_TOLERANCE_MIN = 10
MAX_TOLERANCE_MIN = 180
HISTORY = 10  # kural başına hatırlanan çalışma sayısı (tekrar önleme)

RETRY_DELAYS = (10.0, 30.0)  # ilk deneme hemen; sonra 10 sn, sonra 30 sn bekleyip dener (toplam 3 deneme)
MIN_STEP_SECONDS = 10.0  # yumuşak geçişte iki adım arası en az
BRIGHT_TOLERANCE = 4  # elle müdahale sayılmayan parlaklık sapması (yüzde puanı)
TEMP_TOLERANCE = 6


class RuleError(ValueError):
    """Kural geçersiz; `code` arayüzde çevrilmiş metne dönüşür (`automation.error_<code>`)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PermanentError(Exception):
    """Yeniden denemenin anlamsız olduğu hata (ışık silinmiş, hazır ayar yok)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# -- saat dilimi ---------------------------------------------------------------------------


class Zone(Protocol):
    """Yerel saat ↔ epoch dönüşümü. Üretimde sistem saati; testte yaz saati kuralları taklit edilir."""

    def local(self, ts: float) -> datetime:
        """Epoch saniyesi -> yerel duvar saati (saat dilimsiz)."""

    def instant(self, naive: datetime) -> float:
        """Yerel duvar saati -> epoch. Belirsiz saatte (sonbahar) ilk, olmayan saatte (ilkbahar) kaydırılmış an."""


class SystemZone:
    def local(self, ts: float) -> datetime:
        return datetime.fromtimestamp(ts)

    def instant(self, naive: datetime) -> float:
        return naive.timestamp()


# -- model -----------------------------------------------------------------------------------

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(text: object) -> tuple[int, int]:
    match = _HHMM.match(str(text).strip())
    if match is None:
        raise RuleError("time")
    return int(match.group(1)), int(match.group(2))


def _int(value: object, code: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise RuleError(code)
    try:
        number = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        raise RuleError(code) from None
    if not low <= number <= high:
        raise RuleError(code)
    return number


def _float(value: object, code: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise RuleError(code)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        raise RuleError(code) from None
    if not math.isfinite(number) or not low <= number <= high:
        raise RuleError(code)
    return number


def clean_name(name: object) -> str:
    return " ".join(str(name).split())


@dataclass
class Trigger:
    kind: str = "time"
    time: str = "07:00"  # "time": HH:MM
    days: list[int] = field(default_factory=lambda: list(ALL_DAYS))  # "time" ve "sun": hangi günler
    event: str = "sunset"  # "sun": "sunrise" | "sunset"
    offset: int = 0  # "sun": dakika; eksi = öncesi, artı = sonrası
    lat: float = 0.0
    lon: float = 0.0

    def validate(self) -> None:
        if self.kind not in TRIGGER_KINDS:
            raise RuleError("trigger")
        if self.kind == "startup":
            return
        if not self.days or any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in self.days):
            raise RuleError("days")
        if self.kind == "time":
            parse_hhmm(self.time)
        else:
            if self.event not in SUN_EVENTS:
                raise RuleError("sun_event")
            _float(self.lat, "coords", -90, 90)
            _float(self.lon, "coords", -180, 180)
            _int(self.offset, "offset", -MAX_OFFSET_MIN, MAX_OFFSET_MIN)

    def to_dict(self) -> dict[str, Any]:
        if self.kind == "startup":
            return {"kind": "startup"}
        base: dict[str, Any] = {"kind": self.kind, "days": sorted(set(self.days))}
        if self.kind == "time":
            base["time"] = self.time
        else:
            base.update({"event": self.event, "offset": self.offset, "lat": self.lat, "lon": self.lon})
        return base

    @classmethod
    def from_dict(cls, data: object) -> Trigger:
        if not isinstance(data, dict):
            raise RuleError("trigger")
        kind = data.get("kind")
        if kind not in TRIGGER_KINDS:
            raise RuleError("trigger")
        if kind == "startup":
            return cls(kind="startup")
        days = data.get("days", list(ALL_DAYS))
        if not isinstance(days, list) or any(not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 6 for d in days):
            raise RuleError("days")
        trigger = cls(kind=kind, days=sorted(set(days)))
        if kind == "time":
            h, m = parse_hhmm(data.get("time"))
            trigger.time = f"{h:02d}:{m:02d}"
        else:
            trigger.event = data.get("event", "")
            trigger.offset = _int(data.get("offset", 0), "offset", -MAX_OFFSET_MIN, MAX_OFFSET_MIN)
            trigger.lat = _float(data.get("lat"), "coords", -90, 90)
            trigger.lon = _float(data.get("lon"), "coords", -180, 180)
        trigger.validate()
        return trigger


@dataclass
class Action:
    kind: str = "power"
    power: bool = True  # "power"
    bright: int = 100  # "brightness", "white", "colour": yüzde 1-100
    temp: int = 0  # "white": 0 sıcak … 100 soğuk
    hue: int = 0  # "colour": 0-360
    sat: int = 1000  # "colour": 0-1000
    preset: str = ""  # "preset": hazır ayarın kimliği ("movie", "u-1a2b3c4d")
    fade_min: int = 0  # 0 = yumuşak geçiş yok

    def validate(self) -> None:
        if self.kind not in ACTION_KINDS:
            raise RuleError("action")
        if self.kind in ("brightness", "white", "colour"):
            _int(self.bright, "bright", 1, 100)
        if self.kind == "white":
            _int(self.temp, "temp", 0, 100)
        if self.kind == "colour":
            _int(self.hue, "hue", 0, 360)
            _int(self.sat, "sat", 0, 1000)
        if self.kind == "preset" and not str(self.preset).strip():
            raise RuleError("preset")
        _int(self.fade_min, "fade", 0, MAX_FADE_MIN)
        if self.fade_min and self.kind == "power":
            raise RuleError("fade_kind")

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {"kind": self.kind}
        if self.kind == "power":
            base["power"] = bool(self.power)
        elif self.kind == "brightness":
            base["bright"] = self.bright
        elif self.kind == "white":
            base.update({"bright": self.bright, "temp": self.temp})
        elif self.kind == "colour":
            base.update({"hue": self.hue, "sat": self.sat, "bright": self.bright})
        else:
            base["preset"] = self.preset
        if self.fade_min:
            base["fade_min"] = self.fade_min
        return base

    @classmethod
    def from_dict(cls, data: object) -> Action:
        if not isinstance(data, dict) or data.get("kind") not in ACTION_KINDS:
            raise RuleError("action")
        action = cls(kind=data["kind"])
        if action.kind == "power":
            if not isinstance(data.get("power"), bool):
                raise RuleError("action")
            action.power = data["power"]
        elif action.kind == "preset":
            action.preset = str(data.get("preset", "")).strip()
        else:
            action.bright = _int(data.get("bright", 100), "bright", 1, 100)
            if action.kind == "white":
                action.temp = _int(data.get("temp", 0), "temp", 0, 100)
            if action.kind == "colour":
                action.hue = _int(data.get("hue", 0), "hue", 0, 360)
                action.sat = _int(data.get("sat", 1000), "sat", 0, 1000)
        action.fade_min = _int(data.get("fade_min", 0), "fade", 0, MAX_FADE_MIN)
        action.validate()
        return action


def new_id() -> str:
    return secrets.token_hex(6)


@dataclass
class Rule:
    id: str = ""
    name: str = ""
    enabled: bool = True
    trigger: Trigger = field(default_factory=Trigger)
    action: Action = field(default_factory=Action)
    all_lights: bool = False  # True: kayıtlı tüm ışıklar
    lights: list[str] = field(default_factory=list)  # değilse: bu cihaz kimlikleri
    armed_at: float = 0.0  # kuralın etkinleştiği an (epoch); bundan önceki planlı saatler "kaçırılmış" sayılmaz

    def validate(self) -> None:
        if not clean_name(self.name) or len(clean_name(self.name)) > MAX_NAME:
            raise RuleError("name")
        self.trigger.validate()
        self.action.validate()
        if not self.all_lights and not self.lights:
            raise RuleError("target")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": clean_name(self.name),
            "enabled": bool(self.enabled),
            "trigger": self.trigger.to_dict(),
            "action": self.action.to_dict(),
            "lights": "all" if self.all_lights else list(self.lights),
            "armed_at": self.armed_at,
        }

    @classmethod
    def from_dict(cls, data: object) -> Rule:
        if not isinstance(data, dict):
            raise RuleError("rule")
        lights = data.get("lights")
        if lights == "all":
            all_lights, ids = True, []
        elif isinstance(lights, list) and all(isinstance(x, str) and x for x in lights):
            all_lights, ids = False, list(dict.fromkeys(lights))
        else:
            raise RuleError("target")
        rule_id = data.get("id")
        armed = data.get("armed_at", 0.0)
        rule = cls(
            id=rule_id if isinstance(rule_id, str) and rule_id else new_id(),
            name=clean_name(data.get("name", "")),
            enabled=data.get("enabled", True) is not False,
            trigger=Trigger.from_dict(data.get("trigger")),
            action=Action.from_dict(data.get("action")),
            all_lights=all_lights,
            lights=ids,
            armed_at=float(armed) if isinstance(armed, (int, float)) and not isinstance(armed, bool) and math.isfinite(armed) else 0.0,
        )
        rule.validate()
        return rule


# -- tetikleyici hesabı -----------------------------------------------------------------------


@dataclass(frozen=True)
class Occurrence:
    ts: float  # planlanan an (epoch saniyesi)
    label: str  # "2026-10-28T07:00": tekrar önleme anahtarı (planlanan günün tarihi + yerel saat)


def occurrence(trigger: Trigger, day: date, zone: Zone) -> Occurrence | None:
    """`day` (yerel takvim günü) için tetikleyicinin planlanan anı; o gün çalışmıyorsa ya da güneş doğmuyorsa None."""
    if trigger.kind not in ("time", "sun") or day.weekday() not in trigger.days:
        return None
    if trigger.kind == "time":
        hour, minute = parse_hhmm(trigger.time)
        ts = zone.instant(datetime(day.year, day.month, day.day, hour, minute))
        return Occurrence(ts, f"{day.isoformat()}T{hour:02d}:{minute:02d}")
    noon = zone.instant(datetime(day.year, day.month, day.day, 12))
    base = datetime.fromtimestamp(noon, timezone.utc).date()
    event_ts = None
    for shift in (0, -1, 1):  # yerel güne düşen olayı bul (UTC günü yerel günden bir gün farklı olabilir)
        candidate = sun.sun_event_ts(base + timedelta(days=shift), trigger.lat, trigger.lon, trigger.event)
        if candidate is not None and zone.local(candidate).date() == day:
            event_ts = candidate
            break
    if event_ts is None:
        return None
    ts = round(event_ts / 60.0) * 60.0 + trigger.offset * 60.0
    return Occurrence(ts, f"{day.isoformat()}T{zone.local(ts).strftime('%H:%M')}")


# -- saklama --------------------------------------------------------------------------------------


def default_path(name: str = "automations.json") -> Path:
    import devices

    return devices.user_data_dir() / name


class RuleStore:
    """`automations.json`: kurallar ve ayarlar. `path=None` ise diske yazmaz."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.rules: list[Rule] = []
        self.tolerance_min = DEFAULT_TOLERANCE_MIN
        self.recovered_from: Path | None = None
        self.problem = False  # dosya bozuktu ya da bazı kurallar atlandı

    @classmethod
    def load(cls, path: Path | None = None) -> RuleStore:
        store = cls(path if path is not None else default_path())
        assert store.path is not None
        data, backup, corrupt = storage.load_json(store.path)
        if corrupt:
            store.problem, store.recovered_from = True, backup
            return store
        if data is None:
            return store
        if not isinstance(data, dict):
            store.problem, store.recovered_from = True, storage.backup_file(store.path)
            return store
        settings = data.get("settings")
        if isinstance(settings, dict):
            try:
                store.tolerance_min = _int(settings.get("tolerance_min", DEFAULT_TOLERANCE_MIN), "tolerance", 1, MAX_TOLERANCE_MIN)
            except RuleError:
                store.problem = True
        items = data.get("rules")
        skipped = 0 if isinstance(items, list) or items is None else 1
        seen: set[str] = set()
        for item in items if isinstance(items, list) else []:
            try:
                rule = Rule.from_dict(item)
            except storage.PARSE_ERRORS:  # RuleError dahil (ValueError alt sınıfı); yanlış tip ya da dev sayı da atlanır
                skipped += 1
                continue
            if rule.id in seen:
                rule.id = new_id()
            seen.add(rule.id)
            store.rules.append(rule)
        if skipped or store.problem:
            store.problem = True
            store.recovered_from = storage.backup_file(store.path)
        return store

    def save(self) -> None:
        if self.path is None:
            return
        payload = {
            "version": STORE_VERSION,
            "settings": {"tolerance_min": self.tolerance_min},
            "rules": [r.to_dict() for r in self.rules],
        }
        storage.write_json_atomic(self.path, payload, private=True)

    def _find(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def get(self, rule_id: str) -> Rule | None:
        """Kuralın kopyası (düzenlemek güvenlidir; kaydetmek için `update` kullanın). `rules` listesi okunur, değiştirilmez."""
        rule = self._find(rule_id)
        return copy.deepcopy(rule) if rule is not None else None

    def add(self, rule: Rule, now: float | None = None) -> Rule:
        """Kuralı kaydeder; kimlik ve kurulma anı atanmış kopyasını döndürür."""
        rule.validate()
        if len(self.rules) >= MAX_RULES:
            raise RuleError("limit")
        stored = copy.deepcopy(rule)
        stored.id = stored.id if stored.id and self._find(stored.id) is None else new_id()
        stored.armed_at = time.time() if now is None else now
        self.rules.append(stored)
        self.save()
        return copy.deepcopy(stored)

    def update(self, rule: Rule, now: float | None = None) -> Rule:
        rule.validate()
        index = next((i for i, r in enumerate(self.rules) if r.id == rule.id), -1)
        if index < 0:
            raise RuleError("unknown")
        old = self.rules[index]
        stored = copy.deepcopy(rule)
        if old.trigger.to_dict() == stored.trigger.to_dict() and (old.enabled or not stored.enabled):
            stored.armed_at = old.armed_at  # zamanı ya da etkinliği değişmediyse kaçırılma hesabı sürer
        else:
            stored.armed_at = time.time() if now is None else now
        self.rules[index] = stored
        self.save()
        return copy.deepcopy(stored)

    def set_enabled(self, rule_id: str, enabled: bool, now: float | None = None) -> Rule:
        rule = self._find(rule_id)
        if rule is None:
            raise RuleError("unknown")
        if enabled and not rule.enabled:
            rule.armed_at = time.time() if now is None else now  # açılışta geçmişteki saatler "kaçırılmış" sayılmaz
        rule.enabled = enabled
        self.save()
        return copy.deepcopy(rule)

    def delete(self, rule_id: str) -> None:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        if len(self.rules) == before:
            raise RuleError("unknown")
        self.save()

    def set_tolerance(self, minutes: int) -> None:
        self.tolerance_min = _int(minutes, "tolerance", 1, MAX_TOLERANCE_MIN)
        self.save()


class EngineState:
    """`automation_state.json`: her kuralın en son çalışan planlı anları (tekrar önleme) ve duraklatma durumu.

    Uygulama yeniden başlasa da aynı planlı an ikinci kez çalışmaz. Bozulursa sıfırlanır (zararsız).
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else None
        self.paused = False
        self.fired: dict[str, list[str]] = {}

    @classmethod
    def load(cls, path: Path | None = None) -> EngineState:
        state = cls(path if path is not None else default_path("automation_state.json"))
        assert state.path is not None
        data, _backup, _corrupt = storage.load_json(state.path)
        if isinstance(data, dict):
            state.paused = data.get("paused") is True
            fired = data.get("fired")
            if isinstance(fired, dict):
                for key, labels in fired.items():
                    if isinstance(key, str) and isinstance(labels, list):
                        state.fired[key] = [x for x in labels if isinstance(x, str)][-HISTORY:]
        return state

    def save(self) -> None:
        if self.path is None:
            return
        try:
            storage.write_json_atomic(self.path, {"version": STORE_VERSION, "paused": self.paused, "fired": self.fired})
        except OSError:
            LOGGER.warning("could not save the automation state")

    def seen(self, rule_id: str, label: str) -> bool:
        return label in self.fired.get(rule_id, ())

    def mark(self, rule_id: str, label: str) -> None:
        labels = self.fired.setdefault(rule_id, [])
        if label not in labels:
            labels.append(label)
            del labels[:-HISTORY]
        self.save()

    def forget(self, rule_id: str) -> None:
        if self.fired.pop(rule_id, None) is not None:
            self.save()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.save()


# -- zamanlayıcı -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Due:
    rule: Rule
    scheduled: float  # planlanan an; başlangıç tetikleyicisinde çağrı anı
    late: float  # planlanandan kaç saniye sonra çalıştırıldı


class Scheduler:
    """Saat verildikçe hangi kuralların çalışması gerektiğini söyler. Çalıştırmaz; yalnızca karar verir.

    * Planlı an `tolerans` dakika içinde ve henüz çalışmadıysa kural çalışır (bilgisayar uyurken kaçırılanlar dahil).
    * Çalışan her planlı an (kural + gün + dakika) kaydedilir; saat geri alınsa da ikinci kez çalışmaz.
    * İleri sıçrayan saat, tolerans dışına düşen eski planlı anları çalıştırmaz.
    """

    def __init__(self, store: RuleStore, state: EngineState, zone: Zone | None = None) -> None:
        self.store, self.state = store, state
        self.zone: Zone = zone or SystemZone()
        self._floor = 0.0  # devam ettirmeden önceki planlı anlar çalışmaz

    @property
    def paused(self) -> bool:
        return self.state.paused

    def pause(self) -> None:
        self.state.set_paused(True)

    def resume(self, now: float) -> None:
        self._floor = now
        self.state.set_paused(False)

    def tick(self, now: float) -> list[Due]:
        if self.state.paused:
            return []
        tolerance = self.store.tolerance_min * 60.0
        today = self.zone.local(now).date()
        due: list[Due] = []
        for rule in self.store.rules:
            if not rule.enabled or rule.trigger.kind == "startup":
                continue
            eligible: list[Occurrence] = []
            for offset in (-1, 0, 1):  # dün/bugün/yarın: kaydırma (gece yarısı, gün doğumu ± dakika) tarihi aşabilir
                occ = occurrence(rule.trigger, today + timedelta(days=offset), self.zone)
                if occ is None or occ.ts > now or now - occ.ts > tolerance:
                    continue
                if occ.ts < rule.armed_at or occ.ts < self._floor or self.state.seen(rule.id, occ.label):
                    continue
                eligible.append(occ)
            if eligible:
                latest = max(eligible, key=lambda o: o.ts)
                for occ in eligible:  # birden çok aday varsa yalnızca en yenisi çalışır, eskiler de "çalıştı" sayılır
                    self.state.mark(rule.id, occ.label)
                due.append(Due(rule, latest.ts, now - latest.ts))
        return due

    def startup_due(self, now: float) -> list[Due]:
        """Uygulama açıldığında çalışacak kurallar (duraklatılmışsa hiçbiri)."""
        if self.state.paused:
            return []
        return [Due(r, now, 0.0) for r in self.store.rules if r.enabled and r.trigger.kind == "startup"]

    def next_run(self, rule: Rule, now: float, days_ahead: int = 8) -> float | None:
        """Kuralın bir sonraki planlı anı (arayüzde "sonraki" için); yok ya da başlangıç tetikleyicisi ise None."""
        if rule.trigger.kind == "startup":
            return None
        today = self.zone.local(now).date()
        best = None
        for offset in range(-1, days_ahead):
            occ = occurrence(rule.trigger, today + timedelta(days=offset), self.zone)
            if occ is not None and occ.ts > now and (best is None or occ.ts < best):
                best = occ.ts
        return best


# -- yumuşak geçiş --------------------------------------------------------------------------------


@dataclass(frozen=True)
class FadeStep:
    at: float  # geçişin başından itibaren saniye
    bright: int
    temp: int | None  # yalnızca beyaz geçişte


def fade_plan(
    start_bright: int,
    end_bright: int,
    minutes: float,
    start_temp: int | None = None,
    end_temp: int | None = None,
    min_interval: float = MIN_STEP_SECONDS,
) -> list[FadeStep]:
    """Başlangıçtan hedefe doğrusal adımlar. İlk adım (at=0) başlangıç değerleridir; sonuncusu tam hedeftir.

    Adım sayısı değişimin büyüklüğü ve `min_interval` ile sınırlıdır; değişmeyen ardışık adımlar atlanır.
    """
    total = max(0.0, minutes * 60.0)
    with_temp = start_temp is not None and end_temp is not None
    change = max(abs(end_bright - start_bright), abs(end_temp - start_temp) if with_temp else 0)
    count = max(1, min(change, int(total // min_interval))) if total > 0 else 1
    steps = [FadeStep(0.0, start_bright, start_temp if with_temp else None)]
    for k in range(1, count + 1):
        frac = k / count
        bright = round(start_bright + (end_bright - start_bright) * frac)
        temp = round(start_temp + (end_temp - start_temp) * frac) if with_temp else None
        last = steps[-1]
        if k < count and bright == last.bright and temp == last.temp:
            continue
        steps.append(FadeStep(total * frac, bright, temp))
    if len(steps) > 1 and (steps[-1].bright, steps[-1].temp) == (steps[0].bright, steps[0].temp):
        return steps[:1]  # başlangıç zaten hedef: bekleme yok
    return steps


# -- komutlar ve çalıştırıcı ------------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    """Bir ışığa gönderilecek tek komut (arka uç bunu cihaza özgü veri noktalarına çevirir)."""

    kind: str  # "power" | "brightness" | "white" | "colour" | "scene" (scene: ışığı aç + mod + değerler)
    on: bool | None = None
    bright: int | None = None
    temp: int | None = None
    hue: int | None = None
    sat: int | None = None
    mode: str | None = None  # "scene": "white" | "colour"


class LightStateLike(Protocol):
    power: bool | None
    mode: str | None
    brightness_pct: int | None
    temp_pct: int | None
    val: int | None


class Backend(Protocol):
    def light_ids(self) -> list[str]: ...

    def light_name(self, light_id: str) -> str | None:
        """Bilinmeyen (silinmiş) ışık için None."""

    async def state(self, light_id: str) -> LightStateLike | None: ...

    async def apply(self, light_id: str, command: Command) -> None:
        """Komutu gönderir; ulaşılamazsa istisna fırlatır."""

    async def release(self, light_id: str) -> None:
        """Bu çalıştırma için açılmış geçici bağlantıları kapatır."""


@dataclass(frozen=True)
class Result:
    rule_id: str
    rule_name: str
    light_id: str
    light_name: str
    status: str  # "ok" | "failed" | "interrupted" | "superseded"
    reason: str = ""  # failed: "unreachable" | "unknown_light" | "preset_missing" | "other"
    detail: str = ""


@dataclass(frozen=True)
class Target:
    kind: str  # eylem türü ("preset" da mod'a göre "white"/"colour" olur)
    mode: str | None  # "white" | "colour" | None (yalnızca parlaklık)
    bright: int
    temp: int
    hue: int
    sat: int


def state_brightness(state: LightStateLike | None) -> int | None:
    if state is None:
        return None
    if state.mode == "colour" and state.val is not None:
        return bright_to_pct(state.val)
    return state.brightness_pct


class Runner:
    """Bir kuralı ışıklara uygular; hata ya da elle müdahale kuralı bozmaz, yalnızca `Result` üretir."""

    def __init__(
        self,
        backend: Backend,
        resolve_preset: Callable[[str], Any | None] | None = None,
        on_result: Callable[[Result], None] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
        describe_error: Callable[[BaseException], str] = str,
    ) -> None:
        self.backend = backend
        self._resolve_preset = resolve_preset or (lambda key: None)
        self._on_result = on_result
        self._sleep, self._clock = sleep, clock
        self._retry_delays = retry_delays
        self._describe = describe_error
        self._generation: dict[str, int] = {}
        self._io_lock: asyncio.Lock | None = None

    def _lock(self) -> asyncio.Lock:
        if self._io_lock is None:  # çalışan olay döngüsüne bağlanması için tembel
            self._io_lock = asyncio.Lock()
        return self._io_lock

    # -- hedef çözme ------------------------------------------------------------------------------

    def _target(self, action: Action) -> Target:
        if action.kind == "preset":
            preset = self._resolve_preset(action.preset)
            if preset is None:
                raise PermanentError("preset_missing")
            return Target("preset", preset.mode, preset.bright, preset.temp, preset.hue, preset.sat)
        if action.kind == "brightness":
            return Target("brightness", None, action.bright, 0, 0, 0)
        if action.kind == "white":
            return Target("white", "white", action.bright, action.temp, 0, 0)
        return Target("colour", "colour", action.bright, 0, action.hue, action.sat)

    @staticmethod
    def _first_command(target: Target, bright: int, temp: int) -> Command:
        if target.mode is None:
            return Command("brightness", bright=bright)
        return Command("scene", mode=target.mode, bright=bright, temp=temp, hue=target.hue, sat=target.sat)

    @staticmethod
    def _step_command(target: Target, bright: int, temp: int) -> Command:
        if target.mode is None:
            return Command("brightness", bright=bright)
        if target.mode == "white":
            return Command("white", bright=bright, temp=temp)
        return Command("colour", hue=target.hue, sat=target.sat, bright=bright)

    # -- giriş --------------------------------------------------------------------------------------

    def target_ids(self, rule: Rule) -> list[str]:
        return self.backend.light_ids() if rule.all_lights else list(rule.lights)

    async def run_rule(self, rule: Rule) -> list[Result]:
        """Kuralı hedef ışıklarda eşzamanlı çalıştırır (Bluetooth işlemleri sırayla). İstisna fırlatmaz."""
        ids = self.target_ids(rule)
        results = await asyncio.gather(*(self._run_light(rule, light_id) for light_id in ids))
        return list(results)

    def _report(self, result: Result) -> Result:
        LOGGER.info("automation %s: %s %s", result.rule_id, result.status, result.reason)
        if self._on_result is not None:
            try:
                self._on_result(result)
            except Exception:  # noqa: BLE001 - dinleyicinin hatası çalıştırmayı bozmasın
                LOGGER.debug("result listener failed", exc_info=True)
        return result

    def _current(self, light_id: str, gen: int) -> bool:
        return self._generation.get(light_id) == gen

    async def _run_light(self, rule: Rule, light_id: str) -> Result:
        name = self.backend.light_name(light_id)
        gen = self._generation[light_id] = self._generation.get(light_id, 0) + 1  # bu ışıktaki eski geçişler durur
        base = {"rule_id": rule.id, "rule_name": rule.name, "light_id": light_id, "light_name": name or ""}
        try:
            if name is None:
                raise PermanentError("unknown_light")
            target = self._target(rule.action)
            if rule.action.kind == "power":
                await self._apply(light_id, Command("power", on=rule.action.power), gen)
                return self._report(Result(status="ok", **base))
            if rule.action.fade_min <= 0:
                await self._apply(light_id, self._first_command(target, target.bright, target.temp), gen)
                return self._report(Result(status="ok", **base))
            return self._report(Result(status=await self._fade(rule.action.fade_min, light_id, gen, target), **base))
        except asyncio.CancelledError:
            raise
        except _Superseded:
            return self._report(Result(status="superseded", **base))
        except PermanentError as exc:
            return self._report(Result(status="failed", reason=exc.reason, **base))
        except _GaveUp as exc:
            return self._report(Result(status="failed", reason="unreachable", detail=self._describe(exc.cause), **base))
        except Exception as exc:  # noqa: BLE001 - hiçbir hata kuralı ya da diğer ışıkları bozmaz
            LOGGER.debug("automation failed", exc_info=True)
            return self._report(Result(status="failed", reason="other", detail=self._describe(exc), **base))
        finally:
            if self._current(light_id, gen):
                try:
                    await self.backend.release(light_id)
                except Exception:  # noqa: BLE001
                    LOGGER.debug("release failed", exc_info=True)

    # -- komut gönderme (yeniden deneme) -----------------------------------------------------------------

    async def _apply(self, light_id: str, command: Command, gen: int) -> None:
        await self._retrying(light_id, gen, lambda: self.backend.apply(light_id, command))

    async def _read_state(self, light_id: str, gen: int) -> LightStateLike | None:
        box: list[LightStateLike | None] = []

        async def read() -> None:
            box.append(await self.backend.state(light_id))

        await self._retrying(light_id, gen, read)
        return box[0]

    async def _retrying(self, light_id: str, gen: int, operation: Callable[[], Awaitable[None]]) -> None:
        """En çok 1 + len(retry_delays) deneme; denemeler arasında artan aralıkla bekler."""
        last: BaseException | None = None
        for attempt, delay in enumerate((0.0, *self._retry_delays)):
            if delay:
                await self._sleep(delay)
            if not self._current(light_id, gen):
                raise _Superseded()
            try:
                async with self._lock():
                    await operation()
                return
            except (asyncio.CancelledError, PermanentError):
                raise
            except Exception as exc:  # noqa: BLE001
                last = exc
                LOGGER.debug("attempt %d failed", attempt + 1, exc_info=True)
        raise _GaveUp(last if last is not None else RuntimeError("unreachable"))

    # -- yumuşak geçiş ---------------------------------------------------------------------------------------

    async def _fade(self, minutes: int, light_id: str, gen: int, target: Target) -> str:
        state = await self._read_state(light_id, gen)
        current = state_brightness(state)
        powered = state is not None and state.power is True
        if target.mode is None:  # yalnızca parlaklık: ışığı açmaz
            start_b = current if current is not None else target.bright
        else:
            start_b = current if powered and current is not None else 1  # kapalı ışık en kısıkından açılır
        if target.mode == "white":
            from_white = powered and state is not None and state.mode == "white" and state.temp_pct is not None
            start_t = state.temp_pct if from_white else target.temp  # type: ignore[union-attr]
            plan = fade_plan(start_b, target.bright, minutes, start_t, target.temp)
        else:
            plan = fade_plan(start_b, target.bright, minutes)
        t0 = self._clock()
        expected: tuple[int, int | None] | None = None
        for index, step in enumerate(plan):
            temp = step.temp if step.temp is not None else target.temp
            if index == 0:
                command = self._first_command(target, step.bright, temp)
            else:
                wait = step.at - (self._clock() - t0)
                if wait > 0:
                    await self._sleep(wait)
                if not self._current(light_id, gen):
                    return "superseded"
                if await self._interrupted(light_id, gen, target, expected):
                    return "interrupted"
                command = self._step_command(target, step.bright, temp)
            await self._apply(light_id, command, gen)
            expected = (step.bright, step.temp)
        return "ok"

    async def _interrupted(self, light_id: str, gen: int, target: Target, expected: tuple[int, int | None] | None) -> bool:
        """Kullanıcı geçiş sırasında ışığa elle dokundu mu? (kapattı, modu/parlaklığı/sıcaklığı değiştirdi)"""
        if expected is None:
            return False
        state = await self._read_state(light_id, gen)
        if state is None:
            return False
        if state.power is False:
            return True
        if target.mode is not None and state.mode is not None and state.mode != target.mode:
            return True
        bright = state_brightness(state)
        if bright is not None and abs(bright - expected[0]) > BRIGHT_TOLERANCE:
            return True
        if target.mode == "white" and expected[1] is not None and state.temp_pct is not None:
            return abs(state.temp_pct - expected[1]) > TEMP_TOLERANCE
        return False


class _Superseded(Exception):
    """Aynı ışıkta daha yeni bir çalıştırma başladı."""


class _GaveUp(Exception):
    def __init__(self, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.cause = cause
