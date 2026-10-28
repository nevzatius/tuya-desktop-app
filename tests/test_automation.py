"""Otomasyon motoru: model/doğrulama, saklama, zamanlayıcı, yumuşak geçiş, yeniden deneme. Qt ve ışık gerekmez."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import automation as au  # noqa: E402
from automation_helpers import DstZone, FakeBackend, FakeState, FixedZone, Preset, Sim, at, local_text, make_rule  # noqa: E402

TR = FixedZone(3)  # Türkiye: yaz saati yok
MON = (2026, 10, 26)  # pazartesi
TUE = (2026, 10, 27)


def scheduler(rules, zone=TR, tolerance=10, state_path=None, now=None):
    """(zamanlayıcı, depo). Kurallar `now` anında eklenmiş sayılır (varsayılan: çok eski)."""
    store = au.RuleStore()
    store.tolerance_min = tolerance
    for rule in rules:
        store.add(rule, now if now is not None else 0.0)
    return au.Scheduler(store, au.EngineState(state_path), zone), store


def run(coro):
    return asyncio.run(coro)


# =============================== model ve doğrulama ===============================


def full_rules() -> list[au.Rule]:
    return [
        make_rule("Sabah", au.Trigger(kind="time", time="07:05", days=[0, 1, 2]), au.Action(kind="power", power=False)),
        make_rule(
            "Gün batımı",
            au.Trigger(kind="sun", event="sunset", offset=-15, lat=41.0, lon=29.0, days=[5, 6]),
            au.Action(kind="white", bright=60, temp=30, fade_min=20),
            all_lights=True,
        ),
        make_rule("Açılış", au.Trigger(kind="startup"), au.Action(kind="preset", preset="movie"), lights=["a", "b"]),
        make_rule("Renk", au.Trigger(kind="time", time="22:30"), au.Action(kind="colour", hue=200, sat=900, bright=40)),
        make_rule("Parlaklık", au.Trigger(kind="time", time="23:00"), au.Action(kind="brightness", bright=5, fade_min=10)),
    ]


def test_rules_roundtrip_through_dict_and_file(tmp_path):
    path = tmp_path / "automations.json"
    store = au.RuleStore(path)
    for rule in full_rules():
        store.add(rule, 1000.0)
    loaded = au.RuleStore.load(path)
    assert not loaded.problem
    assert [r.to_dict() for r in loaded.rules] == [r.to_dict() for r in store.rules]
    assert [r.name for r in loaded.rules] == ["Sabah", "Gün batımı", "Açılış", "Renk", "Parlaklık"]
    assert loaded.rules[1].all_lights and loaded.rules[1].action.fade_min == 20 and loaded.rules[1].trigger.offset == -15
    assert loaded.rules[2].lights == ["a", "b"] and loaded.rules[0].action.power is False


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda r: setattr(r.trigger, "time", "25:00"), "time"),
        (lambda r: setattr(r.trigger, "time", "7:5"), "time"),
        (lambda r: setattr(r.trigger, "time", ""), "time"),
        (lambda r: setattr(r.trigger, "days", []), "days"),
        (lambda r: setattr(r.trigger, "days", [7]), "days"),
        (lambda r: setattr(r.trigger, "kind", "weekly"), "trigger"),
        (lambda r: setattr(r.action, "kind", "disco"), "action"),
        (lambda r: setattr(r, "name", "  "), "name"),
        (lambda r: setattr(r, "name", "x" * (au.MAX_NAME + 1)), "name"),
        (lambda r: setattr(r, "lights", []), "target"),
    ],
)
def test_validation_codes_for_time_rules(mutate, code):
    rule = make_rule()
    mutate(rule)
    with pytest.raises(au.RuleError) as err:
        rule.validate()
    assert err.value.code == code


@pytest.mark.parametrize(
    ("trigger", "code"),
    [
        (au.Trigger(kind="sun", event="noon", lat=41, lon=29), "sun_event"),
        (au.Trigger(kind="sun", event="sunset", lat=91, lon=29), "coords"),
        (au.Trigger(kind="sun", event="sunset", lat=41, lon=181), "coords"),
        (au.Trigger(kind="sun", event="sunset", lat=float("nan"), lon=29), "coords"),
        (au.Trigger(kind="sun", event="sunset", lat=41, lon=29, offset=au.MAX_OFFSET_MIN + 1), "offset"),
    ],
)
def test_validation_codes_for_sun_rules(trigger, code):
    with pytest.raises(au.RuleError) as err:
        make_rule(trigger=trigger).validate()
    assert err.value.code == code


@pytest.mark.parametrize(
    ("action", "code"),
    [
        (au.Action(kind="brightness", bright=0), "bright"),
        (au.Action(kind="white", bright=101, temp=0), "bright"),
        (au.Action(kind="white", bright=50, temp=101), "temp"),
        (au.Action(kind="colour", bright=50, hue=361, sat=0), "hue"),
        (au.Action(kind="colour", bright=50, hue=0, sat=1001), "sat"),
        (au.Action(kind="preset", preset=" "), "preset"),
        (au.Action(kind="white", bright=50, temp=0, fade_min=au.MAX_FADE_MIN + 1), "fade"),
        (au.Action(kind="power", power=True, fade_min=5), "fade_kind"),
    ],
)
def test_validation_codes_for_actions(action, code):
    with pytest.raises(au.RuleError) as err:
        make_rule(action=action).validate()
    assert err.value.code == code


def test_from_dict_rejects_wrong_types_instead_of_guessing():
    good = make_rule().to_dict()
    cases = [
        None,
        [],
        {**good, "trigger": "07:00"},
        {**good, "action": None},
        {**good, "lights": "salon"},
        {**good, "lights": [1, 2]},
        {**good, "trigger": {"kind": "time", "time": 700, "days": [0]}},
        {**good, "trigger": {"kind": "time", "time": "07:00", "days": [True]}},
        {**good, "trigger": {"kind": "time", "time": "07:00", "days": [[1]]}},
        {**good, "action": {"kind": "brightness", "bright": True}},
        {**good, "action": {"kind": "power", "power": "yes"}},
        {**good, "action": {"kind": "brightness", "bright": "çok"}},
    ]
    for case in cases:
        with pytest.raises(au.RuleError):
            au.Rule.from_dict(case)


def test_unknown_fields_are_ignored_and_ids_are_generated():
    data = make_rule("Eksik kimlik").to_dict()
    data.pop("id")
    data["gelecek_alan"] = {"x": 1}
    rule = au.Rule.from_dict(data)
    assert rule.id and rule.name == "Eksik kimlik"


# =============================== saklama ===============================


@pytest.mark.parametrize("content", ["{bozuk", "", "[]", "42", '"metin"'])
def test_corrupt_automations_file_is_backed_up_and_starts_empty(tmp_path, content):
    path = tmp_path / "automations.json"
    path.write_text(content, encoding="utf-8")
    store = au.RuleStore.load(path)
    assert store.problem and store.rules == [] and store.recovered_from is not None
    assert store.recovered_from.read_text(encoding="utf-8") == content
    store.add(make_rule(), 5.0)  # yeni kural yazılabilir
    assert len(au.RuleStore.load(path).rules) == 1


def test_invalid_rules_are_skipped_but_valid_ones_and_a_backup_survive(tmp_path):
    path = tmp_path / "automations.json"
    good = make_rule("İyi").to_dict()
    path.write_text(
        json.dumps({"version": 1, "settings": {"tolerance_min": 25}, "rules": [good, {"id": "x"}, "metin", {**good, "id": "başka", "name": ""}]}),
        encoding="utf-8",
    )
    store = au.RuleStore.load(path)
    assert [r.name for r in store.rules] == ["İyi"] and store.tolerance_min == 25
    assert store.problem and store.recovered_from is not None and store.recovered_from.exists()


def test_duplicate_ids_get_fresh_ones_and_bad_settings_fall_back(tmp_path):
    path = tmp_path / "automations.json"
    rule = make_rule("Aynı").to_dict()
    path.write_text(json.dumps({"settings": {"tolerance_min": 9999}, "rules": [rule, rule]}), encoding="utf-8")
    store = au.RuleStore.load(path)
    assert len(store.rules) == 2 and store.rules[0].id != store.rules[1].id
    assert store.tolerance_min == au.DEFAULT_TOLERANCE_MIN and store.problem


def test_missing_file_is_a_normal_first_start_and_nothing_is_written_until_changed(tmp_path):
    path = tmp_path / "automations.json"
    store = au.RuleStore.load(path)
    assert not store.problem and store.rules == [] and not path.exists()


def test_file_holds_light_ids_but_never_keys(tmp_path):
    path = tmp_path / "automations.json"
    au.RuleStore(path).add(make_rule(lights=["bf0123456789abcdefghij"]), 1.0)
    text = path.read_text(encoding="utf-8")
    assert "bf0123456789abcdefghij" in text
    for forbidden in ("local_key", "secret", "uuid", "address"):
        assert forbidden not in text


def test_store_rejects_invalid_rules_unknown_ids_and_too_many(tmp_path):
    store = au.RuleStore(tmp_path / "a.json")
    with pytest.raises(au.RuleError):
        store.add(make_rule(name=""), 1.0)
    with pytest.raises(au.RuleError) as err:
        store.update(make_rule(), 1.0)
    assert err.value.code == "unknown"
    with pytest.raises(au.RuleError):
        store.delete("yok")
    for index in range(au.MAX_RULES):
        store.add(make_rule(f"K{index}"), 1.0)
    with pytest.raises(au.RuleError) as err:
        store.add(make_rule("fazla"), 1.0)
    assert err.value.code == "limit"


def test_crud_and_tolerance_setting_persist(tmp_path):
    path = tmp_path / "automations.json"
    store = au.RuleStore(path)
    rule = store.add(make_rule("A"), 10.0)
    assert rule.id and rule.armed_at == 10.0
    rule.name = "B"
    store.update(rule, 20.0)
    store.set_enabled(rule.id, False, 30.0)
    store.set_tolerance(25)
    with pytest.raises(au.RuleError):
        store.set_tolerance(0)
    loaded = au.RuleStore.load(path)
    assert loaded.rules[0].name == "B" and not loaded.rules[0].enabled and loaded.tolerance_min == 25
    loaded.delete(rule.id)
    assert au.RuleStore.load(path).rules == []


def test_editing_the_time_rearms_but_renaming_does_not(tmp_path):
    store = au.RuleStore()
    rule = store.add(make_rule(), 100.0)
    rule.name = "Yeni ad"
    assert store.update(rule, 200.0).armed_at == 100.0
    rule.trigger.time = "08:00"
    assert store.update(rule, 300.0).armed_at == 300.0
    store.set_enabled(rule.id, False, 400.0)
    assert store.get(rule.id).armed_at == 300.0  # kapatmak yeniden kurmaz
    store.set_enabled(rule.id, True, 500.0)
    assert store.get(rule.id).armed_at == 500.0


def test_engine_state_roundtrip_corruption_and_history_cap(tmp_path):
    path = tmp_path / "automation_state.json"
    state = au.EngineState(path)
    for day in range(au.HISTORY + 5):
        state.mark("r1", f"2026-10-{day + 1:02d}T07:00")
    state.set_paused(True)
    loaded = au.EngineState.load(path)
    assert loaded.paused and len(loaded.fired["r1"]) == au.HISTORY and loaded.seen("r1", f"2026-10-{au.HISTORY + 5:02d}T07:00")
    assert not loaded.seen("r1", "2026-10-01T07:00")  # en eskiler düştü
    path.write_text("{bozuk", encoding="utf-8")
    fresh = au.EngineState.load(path)
    assert not fresh.paused and fresh.fired == {}


# =============================== zamanlayıcı ===============================


def ticks(sched, zone, start, minutes, step_s=30):
    """start'tan itibaren `minutes` dakika boyunca step_s aralıkla tick; çalışanların (planlı, kural adı) listesi."""
    fired = []
    t = start
    end = start + minutes * 60
    while t <= end:
        for due in sched.tick(t):
            fired.append((local_text(zone, due.scheduled), due.rule.name, round(due.late)))
        t += step_s
    return fired


def test_time_rule_fires_exactly_once_at_its_minute():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))])
    assert ticks(sched, TR, at(TR, *MON, 6, 50), 30) == [("2026-10-26 07:00", "Sabah", 0)]


def test_not_due_a_second_before_and_due_on_the_second():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))])
    assert sched.tick(at(TR, *MON, 6, 59, 59)) == []
    assert [d.rule.name for d in sched.tick(at(TR, *MON, 7, 0, 0))] == ["Sabah"]
    assert sched.tick(at(TR, *MON, 7, 0, 1)) == []  # aynı dakikada ikinci kez çalışmaz


def test_days_of_week_are_respected():
    sched, _ = scheduler([make_rule("İş günü", au.Trigger(kind="time", time="07:00", days=[0, 2]))])  # Pzt, Çar
    fired = []
    for day in range(26, 32):  # 26 Ekim Pzt ... 31 Ekim Cmt
        fired += ticks(sched, TR, at(TR, 2026, 10, day, 6, 59), 2)
    assert [f[0] for f in fired] == ["2026-10-26 07:00", "2026-10-28 07:00"]


def test_rule_at_midnight_boundary_and_day_semantics():
    monday_late, _ = scheduler([make_rule("Pzt gece", au.Trigger(kind="time", time="23:58", days=[0]))])
    assert monday_late.tick(at(TR, *MON, 23, 57, 59)) == []
    assert [d.rule.name for d in monday_late.tick(at(TR, *MON, 23, 58, 0))] == ["Pzt gece"]
    assert monday_late.tick(at(TR, *TUE, 0, 1, 0)) == []  # gece yarısını geçince tekrar çalışmaz
    tuesday_midnight, _ = scheduler([make_rule("Sal gece yarısı", au.Trigger(kind="time", time="00:00", days=[1]))])
    assert tuesday_midnight.tick(at(TR, *MON, 23, 59, 59)) == []  # henüz salı değil
    assert [d.rule.name for d in tuesday_midnight.tick(at(TR, *TUE, 0, 0, 10))] == ["Sal gece yarısı"]


def test_missed_across_midnight_counts_for_the_scheduled_day():
    sched, _ = scheduler([make_rule("Pzt gece", au.Trigger(kind="time", time="23:58", days=[0]))])
    due = sched.tick(at(TR, *TUE, 0, 3, 0))  # uyanınca salıya geçmiş; planlı an pazartesi
    assert [(local_text(TR, d.scheduled), round(d.late)) for d in due] == [("2026-10-26 23:58", 300)]
    assert sched.tick(at(TR, *TUE, 0, 4, 0)) == []


def test_missed_rule_runs_once_within_tolerance_then_never():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], tolerance=10)
    due = sched.tick(at(TR, *MON, 7, 6, 0))  # bilgisayar 7:00'de uykudaydı, 7:06'da uyandı
    assert [round(d.late) for d in due] == [360]
    assert sched.tick(at(TR, *MON, 7, 6, 30)) == [] and sched.tick(at(TR, *MON, 7, 7, 0)) == []


def test_missed_rule_is_skipped_after_the_tolerance():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], tolerance=10)
    assert sched.tick(at(TR, *MON, 7, 10, 1)) == []  # 10 dk 1 sn: geç
    assert sched.tick(at(TR, *MON, 9, 0, 0)) == [] and sched.tick(at(TR, *MON, 20, 0, 0)) == []
    assert [d.rule.name for d in sched.tick(at(TR, *TUE, 7, 0, 0))] == ["Sabah"]  # ertesi gün normal


def test_tolerance_boundary_is_inclusive_and_configurable():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], tolerance=3)
    assert [d.rule.name for d in sched.tick(at(TR, *MON, 7, 3, 0))] == ["Sabah"]  # tam 3 dk
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], tolerance=3)
    assert sched.tick(at(TR, *MON, 7, 3, 1)) == []
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], tolerance=60)
    assert len(sched.tick(at(TR, *MON, 7, 59, 0))) == 1


def test_clock_moved_back_does_not_repeat_a_rule_that_already_ran():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))])
    assert len(sched.tick(at(TR, *MON, 7, 0, 0))) == 1
    # kullanıcı saati 1 saat geri aldı: 06:00'dan tekrar 07:05'e kadar
    assert ticks(sched, TR, at(TR, *MON, 6, 0), 65) == []


def test_clock_moved_back_across_midnight_still_does_not_repeat():
    sched, _ = scheduler([make_rule("Gece", au.Trigger(kind="time", time="23:58"))])
    assert len(sched.tick(at(TR, *MON, 23, 58, 0))) == 1
    assert sched.tick(at(TR, *TUE, 0, 1, 0)) == []
    assert ticks(sched, TR, at(TR, *MON, 23, 50), 15) == []  # saat geri: pazartesi 23:50'ye döndü
    assert len(ticks(sched, TR, at(TR, *TUE, 23, 57), 3)) == 1  # ertesi günün planlı anı yine çalışır


def test_clock_jump_forward_skips_old_occurrences_and_runs_the_current_one():
    early = make_rule("Erken", au.Trigger(kind="time", time="07:00"))
    near = make_rule("Yakın", au.Trigger(kind="time", time="11:55"))
    sched, _ = scheduler([early, near])
    assert sched.tick(at(TR, *MON, 6, 0, 0)) == []
    due = sched.tick(at(TR, *MON, 12, 0, 0))  # saat 6'dan 12'ye sıçradı
    assert [d.rule.name for d in due] == ["Yakın"]  # 07:00 tolerans dışı atlandı, 11:55 yakalandı


def test_dedupe_survives_an_app_restart(tmp_path):
    path = tmp_path / "automation_state.json"
    rule = make_rule("Sabah", au.Trigger(kind="time", time="07:00"))
    first, store = scheduler([rule], state_path=path)
    assert len(first.tick(at(TR, *MON, 7, 0, 5))) == 1
    second = au.Scheduler(store, au.EngineState.load(path), TR)  # uygulama yeniden başladı (7:02)
    assert second.tick(at(TR, *MON, 7, 2, 0)) == []


def test_rule_created_just_after_its_time_does_not_fire_retroactively():
    store = au.RuleStore()
    store.add(make_rule("Yeni", au.Trigger(kind="time", time="07:00")), at(TR, *MON, 7, 4, 0))
    sched = au.Scheduler(store, au.EngineState(), TR)
    assert sched.tick(at(TR, *MON, 7, 5, 0)) == []
    assert len(sched.tick(at(TR, *TUE, 7, 0, 0))) == 1
    # kapalı kuralı 7:04'te açmak da geçmişi çalıştırmaz
    store2 = au.RuleStore()
    rule = store2.add(make_rule("Kapalı", au.Trigger(kind="time", time="07:00"), enabled=False), 0.0)
    sched2 = au.Scheduler(store2, au.EngineState(), TR)
    store2.set_enabled(rule.id, True, at(TR, *MON, 7, 4, 0))
    assert sched2.tick(at(TR, *MON, 7, 5, 0)) == []


def test_disabled_rule_never_fires():
    sched, _ = scheduler([make_rule("Kapalı", enabled=False)])
    assert ticks(sched, TR, at(TR, *MON, 6, 55), 10) == []


def test_pause_stops_everything_and_resume_does_not_replay_the_paused_time():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))])
    sched.pause()
    assert sched.paused and ticks(sched, TR, at(TR, *MON, 6, 55), 10) == []
    sched.resume(at(TR, *MON, 7, 5, 0))  # tolerans içinde ama duraklatılmışken geçti: çalışmamalı
    assert sched.tick(at(TR, *MON, 7, 6, 0)) == []
    assert len(sched.tick(at(TR, *TUE, 7, 0, 0))) == 1


def test_pause_state_persists(tmp_path):
    path = tmp_path / "automation_state.json"
    sched, store = scheduler([make_rule()], state_path=path)
    sched.pause()
    again = au.Scheduler(store, au.EngineState.load(path), TR)
    assert again.paused and again.tick(at(TR, *MON, 7, 0, 0)) == []


def test_startup_rules_run_on_demand_and_respect_enabled_and_pause():
    startup = make_rule("Açılış", au.Trigger(kind="startup"))
    other = make_rule("Saat")
    off = make_rule("Kapalı açılış", au.Trigger(kind="startup"), enabled=False)
    sched, _ = scheduler([startup, other, off])
    now = at(TR, *MON, 12, 0)
    assert [d.rule.name for d in sched.startup_due(now)] == ["Açılış"]
    assert [d.rule.name for d in sched.startup_due(now + 1)] == ["Açılış"]  # her açılışta
    assert [d.rule.name for d in sched.tick(now)] == []  # zamanlayıcı başlangıç kurallarını çalıştırmaz
    sched.pause()
    assert sched.startup_due(now) == []


def test_next_run_for_ui():
    sched, _ = scheduler([make_rule(trigger=au.Trigger(kind="time", time="07:00", days=[1]))])
    rule = sched.store.rules[0]
    nxt = sched.next_run(rule, at(TR, *MON, 8, 0))
    assert local_text(TR, nxt) == "2026-10-27 07:00"
    assert sched.next_run(make_rule(trigger=au.Trigger(kind="startup")), 0) is None


# -- yaz saati --------------------------------------------------------------------------------------

DST = DstZone()


def test_dst_spring_forward_nonexistent_time_shifts_to_the_valid_one():
    sched, _ = scheduler([make_rule("02:30", au.Trigger(kind="time", time="02:30"))], zone=DST)
    spring = (2026, 3, 29)
    assert sched.tick(at(DST, *spring, 1, 59, 0)) == []
    assert sched.tick(at(DST, *spring, 3, 29, 0)) == []  # 02:30 yok; 03:30'a kayar
    due = sched.tick(at(DST, *spring, 3, 30, 0))
    assert [local_text(DST, d.scheduled) for d in due] == ["2026-03-29 03:30"]
    assert sched.tick(at(DST, *spring, 3, 31, 0)) == []


def test_dst_normal_rules_keep_their_wall_clock_time_across_the_change():
    sched, _ = scheduler([make_rule("Sabah", au.Trigger(kind="time", time="07:00"))], zone=DST)
    saturday = at(DST, 2026, 3, 28, 7, 0)
    sunday = at(DST, 2026, 3, 29, 7, 0)
    assert len(sched.tick(saturday)) == 1 and len(sched.tick(sunday)) == 1
    assert sunday - saturday == 23 * 3600  # o gün 23 saat sürdü; kural yine duvar saatiyle 07:00
    assert sched.tick(sunday + 23 * 3600) == []  # ertesi gün 06:00 değil


def test_dst_fall_back_ambiguous_time_runs_only_once():
    sched, _ = scheduler([make_rule("02:30", au.Trigger(kind="time", time="02:30"))], zone=DST, tolerance=90)
    first = DST.AUTUMN - 3600 + 1800  # 25 Ekim 02:30 (yaz saati, 1. kez) = 00:30 UTC
    second = first + 3600  # aynı duvar saati 02:30, bu kez kış saati
    assert local_text(DST, first) == local_text(DST, second) == "2026-10-25 02:30"
    assert len(sched.tick(first)) == 1
    assert sched.tick(second) == []  # ikinci 02:30'da tekrar çalışmaz (tolerans içinde olsa bile)
    assert sched.tick(second + 20 * 60) == []


def test_dst_fall_back_rule_after_the_repeated_hour_runs_at_its_time():
    sched, _ = scheduler([make_rule("03:30", au.Trigger(kind="time", time="03:30"))], zone=DST)
    assert sched.tick(at(DST, 2026, 10, 25, 3, 29)) == []
    assert len(sched.tick(at(DST, 2026, 10, 25, 3, 30))) == 1


# -- gün doğumu / batımı -----------------------------------------------------------------------------

ISTANBUL = {"lat": 41.0082, "lon": 28.9784}
SOLSTICE = (2026, 6, 21)


def sun_rule(event="sunset", offset=0, days=None, **where):
    where = where or ISTANBUL
    return make_rule(
        f"{event}{offset:+d}", au.Trigger(kind="sun", event=event, offset=offset, days=days or list(au.ALL_DAYS), **where)
    )


def first_due(rule, zone, day, hours=24):
    sched, _ = scheduler([rule], zone=zone)
    t = at(zone, *day, 0, 0)
    for _ in range(hours * 60):
        due = sched.tick(t)
        if due:
            return zone.local(due[0].scheduled)
        t += 60
    return None


def test_sunset_rule_fires_at_the_known_sunset_time():
    when = first_due(sun_rule("sunset"), TR, SOLSTICE)
    assert abs((when.hour * 60 + when.minute) - (20 * 60 + 39)) <= 3  # İstanbul 21 Haziran batımı ≈ 20:39 (+03)


def test_sunrise_rule_and_offsets_before_and_after():
    rise = first_due(sun_rule("sunrise"), TR, SOLSTICE)
    assert abs((rise.hour * 60 + rise.minute) - (5 * 60 + 32)) <= 3
    before = first_due(sun_rule("sunset", offset=-30), TR, SOLSTICE)
    after = first_due(sun_rule("sunset", offset=+15), TR, SOLSTICE)
    base = first_due(sun_rule("sunset"), TR, SOLSTICE)
    minutes = lambda d: d.hour * 60 + d.minute  # noqa: E731
    assert minutes(base) - minutes(before) == 30 and minutes(after) - minutes(base) == 15


def test_sun_rule_with_offset_past_midnight_is_caught_on_the_next_calendar_day():
    late = sun_rule("sunset", offset=+300)  # 20:39 + 5 sa = ertesi gün 01:39
    sched, _ = scheduler([late])
    due = sched.tick(at(TR, 2026, 6, 22, 1, 42))
    assert len(due) == 1
    minute = TR.local(due[0].scheduled)
    assert minute.day == 22 and abs(minute.hour * 60 + minute.minute - (60 + 39)) <= 3  # 20:39 + 5 sa ≈ ertesi gün 01:39


def test_sun_rule_respects_days_and_fires_at_most_once_a_day():
    saturday_only = sun_rule("sunset", days=[5])  # 2026-06-20 Cumartesi
    sched, _ = scheduler([saturday_only])
    fired = ticks(sched, TR, at(TR, 2026, 6, 19, 0, 0), 4 * 24 * 60, step_s=60)
    assert [f[0][:10] for f in fired] == ["2026-06-20"]


def test_sun_rule_where_the_sun_does_not_rise_never_fires():
    arctic = sun_rule("sunrise", lat=69.6496, lon=18.9560)
    sched, _ = scheduler([arctic], zone=FixedZone(2))
    assert ticks(sched, FixedZone(2), at(FixedZone(2), 2026, 6, 21, 0, 0), 24 * 60, step_s=600) == []


def test_sun_rule_follows_the_season():
    summer = first_due(sun_rule("sunset"), TR, SOLSTICE)
    winter = first_due(sun_rule("sunset"), TR, (2026, 12, 21))
    assert summer.hour == 20 and winter.hour == 17


# =============================== yumuşak geçiş planı ===============================


def test_fade_down_over_thirty_minutes_is_smooth_and_ends_on_target():
    plan = au.fade_plan(80, 10, 30)
    assert plan[0] == au.FadeStep(0.0, 80, None) and plan[-1].bright == 10 and plan[-1].at == 1800
    brights = [s.bright for s in plan]
    assert brights == sorted(brights, reverse=True) and len(plan) == 71  # her adımda %1
    gaps = [b.at - a.at for a, b in zip(plan, plan[1:])]
    assert min(gaps) >= au.MIN_STEP_SECONDS and max(gaps) < 30


def test_fade_up_short_duration_uses_fewer_steps_so_the_light_is_not_flooded():
    plan = au.fade_plan(1, 100, 1)  # 1 dakika
    assert len(plan) - 1 <= 6 and plan[-1] == au.FadeStep(60.0, 100, None)
    assert all(b.at - a.at >= au.MIN_STEP_SECONDS for a, b in zip(plan, plan[1:]))


def test_fade_with_white_temperature_moves_both_linearly():
    plan = au.fade_plan(50, 100, 10, start_temp=0, end_temp=100)
    middle = min(plan, key=lambda s: abs(s.at - 300))
    assert (plan[0].bright, plan[0].temp) == (50, 0) and (plan[-1].bright, plan[-1].temp) == (100, 100)
    assert abs(middle.bright - 75) <= 2 and abs(middle.temp - 50) <= 2


def test_fade_that_changes_little_has_few_steps_and_no_change_has_one():
    assert [s.bright for s in au.fade_plan(50, 52, 30)] == [50, 51, 52]
    assert au.fade_plan(40, 40, 30) == [au.FadeStep(0.0, 40, None)]
    assert au.fade_plan(40, 40, 30, 20, 20) == [au.FadeStep(0.0, 40, 20)]


def test_fade_steps_strictly_increase_in_time_and_never_repeat_a_value():
    for args in [(100, 1, 120), (1, 3, 5), (20, 21, 1), (90, 10, 7)]:
        plan = au.fade_plan(*args)
        assert all(b.at > a.at for a, b in zip(plan, plan[1:]))
        assert all((b.bright, b.temp) != (a.bright, a.temp) for a, b in zip(plan, plan[1:]))


# =============================== çalıştırıcı ===============================


def make_runner(backend, sim=None, presets=None, results=None, retry_delays=au.RETRY_DELAYS):
    sim = sim or Sim()
    return (
        au.Runner(
            backend,
            resolve_preset=(presets or {}).get,
            on_result=(results.append if results is not None else None),
            sleep=sim.sleep,
            clock=sim.clock,
            retry_delays=retry_delays,
        ),
        sim,
    )


def test_power_action_sends_one_power_command_to_the_selected_light():
    backend = FakeBackend()
    runner, _ = make_runner(backend)
    results = run(runner.run_rule(make_rule(action=au.Action(kind="power", power=False))))
    assert backend.calls == [("light-1", au.Command("power", on=False))]
    assert [r.status for r in results] == ["ok"] and backend.released == ["light-1"]


def test_each_action_kind_becomes_the_right_command():
    backend = FakeBackend()
    runner, _ = make_runner(backend, presets={"movie": Preset("colour", 20, hue=28, sat=900), "u-1": Preset("white", 85, temp=45)})
    actions = [
        au.Action(kind="brightness", bright=30),
        au.Action(kind="white", bright=60, temp=25),
        au.Action(kind="colour", bright=40, hue=200, sat=900),
        au.Action(kind="preset", preset="movie"),
        au.Action(kind="preset", preset="u-1"),
    ]
    for action in actions:
        run(runner.run_rule(make_rule(action=action)))
    assert backend.commands() == [
        au.Command("brightness", bright=30),
        au.Command("scene", mode="white", bright=60, temp=25, hue=0, sat=0),
        au.Command("scene", mode="colour", bright=40, temp=0, hue=200, sat=900),
        au.Command("scene", mode="colour", bright=20, temp=0, hue=28, sat=900),
        au.Command("scene", mode="white", bright=85, temp=45, hue=0, sat=0),
    ]


def test_all_lights_target_reaches_every_saved_light_and_specific_targets_only_those():
    backend = FakeBackend(names={"a": "Salon", "b": "Yatak", "c": "Mutfak"})
    runner, _ = make_runner(backend)
    run(runner.run_rule(make_rule(all_lights=True)))
    assert sorted(light for light, _ in backend.calls) == ["a", "b", "c"]
    backend.calls.clear()
    run(runner.run_rule(make_rule(lights=["a", "c"])))
    assert sorted(light for light, _ in backend.calls) == ["a", "c"]


def test_removed_light_fails_that_light_only_and_the_rest_still_run():
    backend = FakeBackend(names={"a": "Salon"})
    results: list[au.Result] = []
    runner, _ = make_runner(backend, results=results)
    out = run(runner.run_rule(make_rule(lights=["silinmiş", "a"])))
    assert [(r.light_id, r.status, r.reason) for r in out] == [("silinmiş", "failed", "unknown_light"), ("a", "ok", "")]
    assert backend.commands() == [au.Command("power", on=True)]


def test_missing_preset_fails_without_touching_the_light():
    backend = FakeBackend()
    runner, _ = make_runner(backend, presets={})
    out = run(runner.run_rule(make_rule(action=au.Action(kind="preset", preset="u-silindi"))))
    assert [(r.status, r.reason) for r in out] == [("failed", "preset_missing")] and backend.calls == []


# -- yeniden deneme -----------------------------------------------------------------------------------


def test_unreachable_light_is_retried_with_growing_delays_then_succeeds():
    backend = FakeBackend(fail={"light-1": 2})
    runner, sim = make_runner(backend)
    out = run(runner.run_rule(make_rule()))
    assert [r.status for r in out] == ["ok"] and sim.sleeps == [10.0, 30.0] and len(backend.calls) == 1


def test_gives_up_after_three_attempts_and_reports_it():
    backend = FakeBackend(fail={"light-1": -1})
    results: list[au.Result] = []
    runner, sim = make_runner(backend, results=results)
    attempts = []
    original = backend.apply

    async def counting(light_id, command):
        attempts.append(command)
        await original(light_id, command)

    backend.apply = counting
    out = run(runner.run_rule(make_rule("Gece")))
    assert len(attempts) == 3 and sim.sleeps == [10.0, 30.0]
    assert [(r.status, r.reason) for r in out] == [("failed", "unreachable")] and "unreachable" in out[0].detail
    assert results == out and out[0].rule_name == "Gece" and out[0].light_name == "Salon"


def test_one_unreachable_light_does_not_stop_the_others_and_nothing_is_raised():
    backend = FakeBackend(names={"a": "Salon", "b": "Yatak"}, fail={"a": -1})
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(make_rule(all_lights=True)))
    assert {r.light_id: r.status for r in out} == {"a": "failed", "b": "ok"}
    # sonraki çalıştırma yine normal çalışır (kural bozulmadı)
    backend.fail.clear()
    again = run(runner.run_rule(make_rule(all_lights=True)))
    assert [r.status for r in again] == ["ok", "ok"]


def test_a_crashing_result_listener_does_not_break_the_run():
    backend = FakeBackend()

    def bad_listener(result):
        raise RuntimeError("dinleyici çöktü")

    runner = au.Runner(backend, on_result=bad_listener, sleep=Sim().sleep)
    assert [r.status for r in run(runner.run_rule(make_rule()))] == ["ok"]


def test_backend_that_raises_unexpected_error_types_is_still_contained():
    class Broken(FakeBackend):
        async def apply(self, light_id, command):
            raise ValueError("beklenmedik")

    runner, _ = make_runner(Broken(), retry_delays=())
    out = run(runner.run_rule(make_rule()))
    assert [(r.status, r.reason) for r in out] == [("failed", "unreachable")]


# -- yumuşak geçiş (çalıştırıcı) ----------------------------------------------------------------------------


def fade_rule(kind="white", minutes=10, **action):
    values = {"white": dict(bright=80, temp=60), "colour": dict(bright=70, hue=200, sat=900), "brightness": dict(bright=80)}[kind]
    values.update(action)
    return make_rule("Geçiş", action=au.Action(kind=kind, fade_min=minutes, **values))


def test_white_fade_from_current_state_ramps_brightness_and_temperature_on_time():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=40, temp_pct=20)})
    runner, sim = make_runner(backend)
    out = run(runner.run_rule(fade_rule("white", 10)))
    commands = backend.commands()
    assert [r.status for r in out] == ["ok"]
    assert commands[0] == au.Command("scene", mode="white", bright=40, temp=20, hue=0, sat=0)
    assert commands[-1] == au.Command("white", bright=80, temp=60)
    levels = [c.bright for c in commands]
    assert levels == sorted(levels) and len(set(levels)) == len(levels)
    assert all(c.kind == "white" for c in commands[1:])
    assert sim.now == pytest.approx(600, abs=1)  # toplam süre 10 dakika


def test_fade_from_an_off_light_starts_at_the_dimmest_level():
    backend = FakeBackend(states={"light-1": FakeState(power=False, mode="white", brightness_pct=90, temp_pct=10)})
    runner, _ = make_runner(backend)
    run(runner.run_rule(fade_rule("white", 5)))
    first = backend.commands()[0]
    assert first.kind == "scene" and first.bright == 1 and first.temp == 60  # kapalıysa sıcaklık hedefte, parlaklık 1'den


def test_colour_fade_keeps_hue_and_saturation_and_changes_only_brightness():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="colour", brightness_pct=None, val=100)})
    runner, _ = make_runner(backend)
    run(runner.run_rule(fade_rule("colour", 4)))
    commands = backend.commands()
    assert commands[0].kind == "scene" and commands[0].mode == "colour"
    assert all(c.hue == 200 and c.sat == 900 for c in commands)
    assert commands[-1] == au.Command("colour", hue=200, sat=900, bright=70)


def test_brightness_fade_never_powers_the_light_on_or_changes_mode():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=20, temp_pct=50)})
    runner, _ = make_runner(backend)
    run(runner.run_rule(fade_rule("brightness", 3)))
    assert {c.kind for c in backend.commands()} == {"brightness"} and backend.commands()[-1].bright == 80


def test_fade_where_nothing_changes_applies_the_target_once_without_waiting():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=80, temp_pct=60)})
    runner, sim = make_runner(backend)
    run(runner.run_rule(fade_rule("white", 30)))
    assert len(backend.calls) == 1 and sim.sleeps == []


def test_manual_brightness_change_during_a_fade_stops_it():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=50)})

    def user_moves_slider(be, light, command, count):
        if count == 4:  # dördüncü komuttan sonra kullanıcı kaydırıcıyı elle 95'e çekti
            be.states[light].brightness_pct = 95

    backend.on_apply = user_moves_slider
    runner, _ = make_runner(backend)
    results: list[au.Result] = []
    runner._on_result = results.append
    out = run(runner.run_rule(fade_rule("white", 10, bright=90, temp=50)))
    assert [r.status for r in out] == ["interrupted"] and len(backend.calls) == 4
    assert backend.states["light-1"].brightness_pct == 95  # kullanıcının değerine dokunulmadı


@pytest.mark.parametrize(
    "interfere",
    [
        lambda st: setattr(st, "power", False),
        lambda st: setattr(st, "mode", "colour"),
        lambda st: setattr(st, "temp_pct", 100),
    ],
    ids=["turned-off", "mode-changed", "temperature-changed"],
)
def test_other_manual_changes_also_stop_the_fade(interfere):
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=10)})
    backend.on_apply = lambda be, light, command, count: interfere(be.states[light]) if count == 3 else None
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(fade_rule("white", 10, bright=90, temp=40)))
    assert [r.status for r in out] == ["interrupted"] and len(backend.calls) == 3


def test_small_drift_within_tolerance_is_not_a_manual_change():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=10)})

    def jitter(be, light, command, count):
        be.states[light].brightness_pct = (command.bright or 0) + (au.BRIGHT_TOLERANCE - 1)

    backend.on_apply = jitter
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(fade_rule("white", 3, bright=60, temp=10)))
    assert [r.status for r in out] == ["ok"] and backend.commands()[-1].bright == 60


def test_unknown_state_does_not_count_as_manual_change():
    class NoState(FakeBackend):
        async def state(self, light_id):
            return None

    backend = NoState(reflect=False)
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(fade_rule("white", 2, bright=30, temp=60)))
    assert [r.status for r in out] == ["ok"] and len(backend.calls) > 2
    assert backend.commands()[-1] == au.Command("white", bright=30, temp=60)


def test_a_newer_run_on_the_same_light_supersedes_a_running_fade_and_keeps_the_connection():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=10)})
    sim = Sim()
    runner, _ = make_runner(backend, sim=sim)
    other = make_rule("Kapat", action=au.Action(kind="power", power=False))
    started = []

    async def interrupt(s):
        if len(s.sleeps) == 3 and not started:
            started.append(True)
            await runner.run_rule(other)  # fade sürerken başka kural aynı ışığı kapatıyor

    sim.hook = interrupt
    out = run(runner.run_rule(fade_rule("white", 10, bright=90, temp=50)))
    assert [r.status for r in out] == ["superseded"]
    assert backend.commands()[-1] == au.Command("power", on=False)  # sonuncu söz sahibi
    assert backend.released == ["light-1"]  # yalnızca yeni çalıştırma bağlantıyı bıraktı


def test_failure_in_the_middle_of_a_fade_is_reported_and_does_not_raise():
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=10)})

    def break_after_three(be, light, command, count):
        if count == 3:
            be.fail[light] = -1

    backend.on_apply = break_after_three
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(fade_rule("white", 10, bright=90, temp=50)))
    assert [(r.status, r.reason) for r in out] == [("failed", "unreachable")] and len(backend.calls) == 3


def test_two_lights_fade_concurrently_and_both_reach_the_target():
    backend = FakeBackend(
        names={"a": "Salon", "b": "Yatak"},
        states={"a": FakeState(brightness_pct=10, temp_pct=10), "b": FakeState(brightness_pct=30, temp_pct=10)},
    )
    runner, _ = make_runner(backend)
    out = run(runner.run_rule(make_rule(all_lights=True, action=au.Action(kind="white", bright=70, temp=40, fade_min=5))))
    assert [r.status for r in out] == ["ok", "ok"]
    assert backend.commands("a")[-1] == au.Command("white", bright=70, temp=40)
    assert backend.commands("b")[-1] == au.Command("white", bright=70, temp=40)
    assert len(backend.commands("a")) > 2 and len(backend.commands("b")) > 2  # ikisi de adım adım ilerledi
