"""Otomasyon kurallarının kullanıcıya gösterilen kısa özet metinleri (etkin dile göre)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import automation as au
from i18n import tr

from .colors import hex_of, hs_rgb

WEEKDAYS = (0, 1, 2, 3, 4)
WEEKEND = (5, 6)


def error_text(error: au.RuleError) -> str:
    return tr(
        f"automation.error_{error.code}",
        max=au.MAX_NAME,
        offset=au.MAX_OFFSET_MIN,
        fade=au.MAX_FADE_MIN,
        limit=au.MAX_RULES,
    )


def days_text(days: list[int]) -> str:
    chosen = tuple(sorted(set(days)))
    if chosen == au.ALL_DAYS:
        return tr("automation.days_all")
    if chosen == WEEKDAYS:
        return tr("automation.days_weekdays")
    if chosen == WEEKEND:
        return tr("automation.days_weekend")
    return ", ".join(tr(f"day.{d}") for d in chosen)


def trigger_text(trigger: au.Trigger) -> str:
    if trigger.kind == "startup":
        return tr("automation.when_startup")
    days = days_text(trigger.days)
    if trigger.kind == "time":
        return tr("automation.when_time", days=days, time=trigger.time)
    if trigger.offset == 0:
        phrase = tr(f"automation.sun_at_{trigger.event}")
    else:
        phrase = tr(f"automation.sun_{'before' if trigger.offset < 0 else 'after'}_{trigger.event}", minutes=abs(trigger.offset))
    return tr("automation.when_sun", days=days, phrase=phrase)


def temp_word(temp: int) -> str:
    return tr("main.warm") if temp < 34 else tr("main.neutral") if temp < 67 else tr("main.cool")


def action_text(action: au.Action, preset_name: Callable[[str], str | None]) -> str:
    if action.kind == "power":
        text = tr("automation.do_power_on" if action.power else "automation.do_power_off")
    elif action.kind == "brightness":
        text = tr("automation.do_brightness", bright=action.bright)
    elif action.kind == "white":
        text = tr("automation.do_white", bright=action.bright, temp=temp_word(action.temp))
    elif action.kind == "colour":
        text = tr("automation.do_colour", hex=hex_of(hs_rgb(action.hue, action.sat)), bright=action.bright)
    else:
        name = preset_name(action.preset)
        text = tr("automation.do_preset", name=name) if name else tr("automation.do_preset_missing")
    if action.fade_min:
        text = f"{text}, {tr('automation.fade_suffix', minutes=action.fade_min)}"
    return text


def targets_text(rule: au.Rule, light_names: dict[str, str]) -> str:
    if rule.all_lights:
        return tr("automation.targets_all")
    return ", ".join(light_names.get(light_id) or tr("automation.target_missing") for light_id in rule.lights)


def summary_text(rule: au.Rule, preset_name: Callable[[str], str | None]) -> str:
    return tr("automation.summary", when=trigger_text(rule.trigger), what=action_text(rule.action, preset_name))


def next_text(ts: float | None, now: float, zone: au.Zone) -> str:
    """"Sonraki: bugün 19:30" / "yarın 07:00" / "Çar 07:00"."""
    if ts is None:
        return tr("automation.next_none")
    when: datetime = zone.local(ts)
    today = zone.local(now).date()
    delta = (when.date() - today).days
    day = tr("automation.today") if delta == 0 else tr("automation.tomorrow") if delta == 1 else tr(f"day.{when.weekday()}")
    return tr("automation.next", when=f"{day} {when:%H:%M}")


def last_text(result: au.Result | None) -> str:
    if result is None:
        return ""
    if result.status == "ok":
        return tr("automation.last_ok")
    if result.status == "interrupted":
        return tr("automation.last_interrupted")
    if result.status == "superseded":
        return tr("automation.last_superseded")
    reason = result.reason if result.reason in ("unreachable", "unknown_light", "preset_missing") else "other"
    return tr("automation.last_failed", reason=tr(f"automation.reason_{reason}"))
