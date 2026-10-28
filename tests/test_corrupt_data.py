"""Bozuk kullanıcı verisi: devices.json, presets.json, automations.json açılışı çökertmez, dosya yedeklenir, geçerli kayıtlar korunur."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import automation as au
import devices as dv
import i18n
import light_app
import light_core as lc
import storage
from ui.presets import PRESETS, PresetStore

NEST = 200_000  # json.loads varsayılan özyineleme sınırını aşar (RecursionError)
GOOD_DEVICE = {"device_id": "dev1", "local_key": "key1key1key1key1", "uuid": "uuid1", "name": "Işık 1"}
GOOD_RULE = {
    "id": "r1",
    "name": "Akşam",
    "trigger": {"kind": "time", "time": "20:00"},
    "action": {"kind": "power", "power": True},
    "lights": "all",
}


def _id(value):
    """Dev boyutlu içerik test adına girmesin (Windows yol uzunluğu sınırı)."""
    return "deep" if isinstance(value, str) and len(value) > 200 else None


def deep(n: int = NEST) -> str:
    return "[" * n + "]" * n


def write(path: Path, content) -> str:
    text = content if isinstance(content, str) else json.dumps(content)
    path.write_text(text, encoding="utf-8")
    return text


def assert_backed_up(store, original: str, path: Path) -> None:
    assert store.problem
    assert store.recovered_from is not None and store.recovered_from.exists()
    assert ".bad-" in store.recovered_from.name and store.recovered_from.parent == path.parent
    assert store.recovered_from.read_text(encoding="utf-8") == original


# =============================== storage.load_json ===============================


@pytest.mark.parametrize("content", ["{bozuk", "", "null", deep(), '{"a":' * NEST + "1" + "}" * NEST], ids=_id)
def test_load_json_treats_unparseable_or_too_deep_files_as_corrupt(tmp_path, content):
    path = tmp_path / "x.json"
    write(path, content)
    data, backup, corrupt = storage.load_json(path)
    assert data is None and corrupt and backup is not None and backup.read_text(encoding="utf-8") == content


def test_load_json_missing_file_is_not_corrupt(tmp_path):
    assert storage.load_json(tmp_path / "yok.json") == (None, None, False)


# =============================== devices.json ===============================


@pytest.mark.parametrize(
    "content",
    [
        "{bozuk",
        "",
        "null",
        "[]",
        '[{"device_id": "a", "local_key": "b"}]',  # kök liste
        '"metin"',
        "42",
        deep(),
        '{"devices": ' + deep() + "}",
    ],
    ids=_id,
)
def test_corrupt_or_wrongly_shaped_devices_file_starts_empty_with_a_backup(tmp_path, content):
    path = tmp_path / "devices.json"
    write(path, content)
    store = dv.DeviceStore.load(path)  # çökmez
    assert len(store) == 0 and store.current() is None and store.selected == ""
    assert_backed_up(store, content, path)


@pytest.mark.parametrize(
    "devices",
    [
        "metin",
        5,
        {"device_id": "dev1"},
        [1, "a", None, [], [[]]],
        [{"device_id": "a"}],
        [{"device_id": 5, "local_key": "k"}],
        [{"device_id": "a", "local_key": ["k"]}],
        [{"device_id": "a", "local_key": "k", "name": 5}],
        [{"device_id": "a", "local_key": "k", "uuid": {"x": 1}}],
        [{"device_id": "a", "local_key": "k", "dps": ["switch_led"]}],
        [{"device_id": "a", "local_key": "k", "dps": {"switch_led": "yirmi"}}],
        [{"device_id": "a", "local_key": "k", "dps": {"switch_led": [20]}}],
        [{"device_id": "a", "local_key": "k", "dps": {"switch_led": True}}],
        [{"device_id": "a", "local_key": "k", "name": json.loads("[" * 900 + "]" * 900)}],
    ],
)
def test_wrongly_typed_devices_are_rejected_with_a_backup(tmp_path, devices):
    path = tmp_path / "devices.json"
    content = write(path, {"version": 1, "selected": "", "devices": devices})
    store = dv.DeviceStore.load(path)
    assert len(store) == 0
    assert_backed_up(store, content, path)


def test_selected_as_a_list_keeps_the_devices_and_falls_back_to_the_first(tmp_path):
    path = tmp_path / "devices.json"
    content = write(path, {"selected": ["dev1"], "devices": [GOOD_DEVICE, {**GOOD_DEVICE, "device_id": "dev2"}]})
    store = dv.DeviceStore.load(path)
    assert [c.device_id for c in store.devices()] == ["dev1", "dev2"] and store.selected == "dev1"
    assert_backed_up(store, content, path)


@pytest.mark.parametrize("selected", [5, {"a": 1}, None, True])
def test_other_wrong_selected_types_do_not_crash(tmp_path, selected):
    path = tmp_path / "devices.json"
    write(path, {"selected": selected, "devices": [GOOD_DEVICE]})
    store = dv.DeviceStore.load(path)
    assert store.selected == "dev1" and len(store) == 1


def test_valid_devices_survive_next_to_broken_ones(tmp_path):
    path = tmp_path / "devices.json"
    content = write(path, {"selected": "dev1", "devices": [GOOD_DEVICE, "bozuk", {"device_id": "x"}, {**GOOD_DEVICE, "device_id": "dev3"}]})
    store = dv.DeviceStore.load(path)
    assert [c.device_id for c in store.devices()] == ["dev1", "dev3"] and store.selected == "dev1"
    assert_backed_up(store, content, path)


def test_a_healthy_devices_file_is_not_flagged_or_backed_up(tmp_path):
    path = tmp_path / "devices.json"
    write(path, {"selected": "dev1", "devices": [{**GOOD_DEVICE, "dps": {"switch_led": "20"}, "watts": "12"}]})
    store = dv.DeviceStore.load(path)
    assert not store.problem and store.recovered_from is None and store.current().dps["switch_led"] == 20
    assert list(tmp_path.glob("*.bad-*")) == []


def test_new_data_can_be_saved_after_a_corrupt_file_and_the_backup_stays(tmp_path):
    path = tmp_path / "devices.json"
    original = write(path, "{bozuk")
    store = dv.DeviceStore.load(path)
    store.add(lc.Config(device_id="dev9", local_key="yeni-anahtar-123456", uuid="u"))
    store.save()
    assert dv.DeviceStore.load(path).selected == "dev9"
    assert store.recovered_from.read_text(encoding="utf-8") == original


def test_load_survives_a_failed_backup(tmp_path, monkeypatch):
    path = tmp_path / "devices.json"
    write(path, "{bozuk")

    def refuse(*_a, **_k):
        raise OSError("disk dolu")

    monkeypatch.setattr(shutil, "copy2", refuse)
    store = dv.DeviceStore.load(path)
    assert store.problem and store.recovered_from is None and len(store) == 0


# -- kullanıcıya gösterilen metin (light_app) ----------------------------------------------------


def test_startup_notice_explains_the_problem_and_names_the_backup_without_a_path(tmp_path):
    path = tmp_path / "devices.json"
    write(path, "{bozuk")
    store = dv.DeviceStore.load(path)
    text = light_app.devices_problem_text(store)
    assert "devices.json" in text and "sihirbaz" in text and store.recovered_from.name in text
    assert str(tmp_path) not in text  # yol (kullanıcı adını içerebilir) gösterilmez
    assert store.current() is None  # light_app bundan sonra kurulum sihirbazını açar


def test_startup_notice_variants_and_languages(tmp_path):
    path = tmp_path / "devices.json"
    write(path, {"devices": [GOOD_DEVICE, "bozuk"]})
    store = dv.DeviceStore.load(path)
    assert "atlandı" in light_app.devices_problem_text(store)  # kısmi: ışıklar korunur, sihirbaz yok
    store.recovered_from = None
    assert "yedeği alınamadı" in light_app.devices_problem_text(store)
    i18n.set_language("en")
    english = light_app.devices_problem_text(store)
    assert "skipped" in english and "could not be backed up" in english
    assert light_app.devices_problem_text(dv.DeviceStore(tmp_path / "temiz.json")) == ""


# =============================== presets.json ===============================


@pytest.mark.parametrize(
    "content",
    ["[]", "[1, 2]", "null", '"metin"', "7", deep(), '{"presets": ' + deep() + "}", '{"hotkeys": ' + deep() + "}"],
    ids=_id,
)
def test_presets_file_with_wrong_root_or_deep_nesting_starts_with_builtins(tmp_path, content):
    path = tmp_path / "presets.json"
    write(path, content)
    store = PresetStore.load(path)  # çökmez
    assert [p.key for p in store.visible()] == [p.key for p in PRESETS] and store.user_presets() == []
    if content.startswith('{"'):  # geçerli JSON ama içeriği yanlış tipte
        assert store.problem
    else:
        assert_backed_up(store, content, path)


DEEP_VALUE = json.loads("[" * 900 + "]" * 900)  # json.loads'un kabul ettiği ama str()/işleme için ağır iç içe değer


@pytest.mark.parametrize(
    "payload",
    [
        {"presets": "metin"},
        {"presets": {"a": 1}},
        {"presets": [1, None, [], "x", {"id": ["u-1"], "name": "A", "mode": "white"}]},
        {"presets": [{"id": "u-aaaa1111", "name": ["Ad"], "mode": "white"}]},
        {"presets": [{"id": "u-aaaa1111", "name": 5, "mode": "white", "bright": [1]}]},
        {"presets": [{"id": "u-aaaa1111", "name": DEEP_VALUE, "mode": "white"}]},
        {"presets": [{"id": "u-aaaa1111", "name": "Ad", "mode": DEEP_VALUE}]},
        {"hidden": "movie", "hotkeys": [1, 2]},
        {"hotkeys": {"movie": ["Ctrl+Alt+A"], "reading": 5, "night": {"a": 1}}},
        {"hotkeys": {"movie": DEEP_VALUE}},
    ],
)
def test_presets_with_wrong_types_never_crash_and_are_backed_up(tmp_path, payload):
    path = tmp_path / "presets.json"
    content = write(path, payload)
    store = PresetStore.load(path)
    assert store.user_presets() == [] and store.hotkeys() == {}
    assert [p.key for p in store.visible()] == [p.key for p in PRESETS]
    assert_backed_up(store, content, path)


def test_presets_with_a_wrongly_typed_number_are_clamped_not_dropped(tmp_path):
    """Sayı alanları yanlış tipteyse varsayılana döner (yerleşik davranış); ad ve mod yine de doğrulanır."""
    path = tmp_path / "presets.json"
    write(path, {"presets": [{"id": "u-aaaa1111", "name": "Derin", "mode": "white", "bright": DEEP_VALUE, "temp": ["x"]}]})
    store = PresetStore.load(path)
    assert [(p.name, p.bright, p.temp) for p in store.user_presets()] == [("Derin", 50, 0)] and not store.problem


# =============================== automations.json ===============================


@pytest.mark.parametrize(
    "content",
    ["[]", "[1]", "null", '"metin"', "7", deep(), '{"rules": ' + deep() + "}", '{"settings": ' + deep() + "}"],
    ids=_id,
)
def test_automations_file_with_wrong_root_or_deep_nesting_starts_empty(tmp_path, content):
    path = tmp_path / "automations.json"
    write(path, content)
    store = au.RuleStore.load(path)  # çökmez
    assert store.rules == []
    if content.startswith('{"'):
        assert store.problem
    else:
        assert_backed_up(store, content, path)


@pytest.mark.parametrize(
    "bad_rule",
    [
        "metin",
        5,
        [],
        {**GOOD_RULE, "armed_at": 10**400},  # float'a çevrilemeyen dev sayı (OverflowError)
        {**GOOD_RULE, "name": json.loads("[" * 900 + "]" * 900)},
        {**GOOD_RULE, "trigger": {"kind": "time", "time": ["20:00"]}},
        {**GOOD_RULE, "trigger": {"kind": "time", "time": json.loads("[" * 900 + "]" * 900)}},
        {**GOOD_RULE, "trigger": {"kind": "time", "time": "20:00", "days": "pzt"}},
        {**GOOD_RULE, "action": {"kind": "brightness", "bright": [50]}},
        {**GOOD_RULE, "lights": [["dev1"]]},
        {**GOOD_RULE, "lights": {"all": True}},
        {**GOOD_RULE, "enabled": [True], "trigger": 5},
    ],
)
def test_wrongly_typed_rules_are_skipped_and_valid_ones_survive(tmp_path, bad_rule):
    path = tmp_path / "automations.json"
    content = write(path, {"version": 1, "settings": {"tolerance_min": [5]}, "rules": [GOOD_RULE, bad_rule, {**GOOD_RULE, "id": "r2"}]})
    store = au.RuleStore.load(path)
    assert [r.id for r in store.rules] == ["r1", "r2"]
    assert_backed_up(store, content, path)


def test_wrong_rules_container_types_do_not_crash(tmp_path):
    for payload in ({"rules": "metin"}, {"rules": {"a": 1}}, {"rules": 5}, {"settings": [1]}, {"settings": {"tolerance_min": "çok"}}):
        path = tmp_path / "automations.json"
        write(path, payload)
        assert au.RuleStore.load(path).rules == []


def test_engine_state_survives_corrupt_and_deep_files(tmp_path):
    path = tmp_path / "automation_state.json"
    for content in (deep(), "{bozuk", "[]", "null", '{"fired": ' + deep() + "}"):
        write(path, content)
        state = au.EngineState.load(path)
        assert state.fired == {} and not state.paused


# =============================== yükleme sınırları ===============================


def padded(payload: dict, size: int) -> str:
    """Geçerli JSON; sonuna boşluk eklenerek tam `size` bayta tamamlanır."""
    text = json.dumps(payload)
    assert len(text) <= size
    return text + " " * (size - len(text))


def test_a_file_over_the_size_limit_is_not_read_and_is_moved_aside(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(padded({"a": 1}, storage.MAX_FILE_BYTES + 1), encoding="ascii")
    data, backup, corrupt = storage.load_json(path)
    assert data is None and corrupt and backup is not None and ".bad-" in backup.name
    assert backup.stat().st_size == storage.MAX_FILE_BYTES + 1 and not path.exists()  # taşındı: dev dosya kopyalanmadı


def test_a_file_exactly_at_the_limit_still_loads(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(padded({"a": 1}, storage.MAX_FILE_BYTES), encoding="ascii")
    assert storage.load_json(path) == ({"a": 1}, None, False)


def test_oversized_files_do_not_crash_any_store(tmp_path):
    big = padded({"devices": [GOOD_DEVICE], "presets": [], "rules": [GOOD_RULE], "fired": {}}, storage.MAX_FILE_BYTES + 10)
    for name, load in (
        ("devices.json", dv.DeviceStore.load),
        ("presets.json", PresetStore.load),
        ("automations.json", au.RuleStore.load),
        ("automation_state.json", au.EngineState.load),
    ):
        path = tmp_path / name
        path.write_text(big, encoding="ascii")
        store = load(path)
        assert getattr(store, "problem", False) or name == "automation_state.json"
        assert list(tmp_path.glob(f"{name}.bad-*")) and not path.exists()
    assert len(dv.DeviceStore.load(tmp_path / "devices.json")) == 0


def test_a_failed_move_of_an_oversized_file_still_does_not_crash(tmp_path, monkeypatch):
    path = tmp_path / "devices.json"
    path.write_text(padded({}, storage.MAX_FILE_BYTES + 1), encoding="ascii")

    def refuse(*_a, **_k):
        raise OSError("kilitli")

    monkeypatch.setattr(storage.os, "replace", refuse)
    store = dv.DeviceStore.load(path)
    assert store.problem and store.recovered_from is None and len(store) == 0


def test_preset_list_is_cut_at_the_limit_and_flagged(tmp_path):
    from ui.presets import MAX_USER_PRESETS

    items = [{"id": f"u-{i:08x}", "name": f"Ayar {i}", "mode": "white", "bright": 50} for i in range(MAX_USER_PRESETS + 5)]
    path = tmp_path / "presets.json"
    content = write(path, {"presets": items})
    store = PresetStore.load(path)
    assert [p.name for p in store.user_presets()] == [f"Ayar {i}" for i in range(MAX_USER_PRESETS)]
    assert_backed_up(store, content, path)
    exact = tmp_path / "exact.json"
    write(exact, {"presets": items[:MAX_USER_PRESETS]})
    assert len(PresetStore.load(exact).user_presets()) == MAX_USER_PRESETS and not PresetStore.load(exact).problem


def test_rule_list_is_cut_at_the_limit_and_flagged(tmp_path):
    rules = [{**GOOD_RULE, "id": f"r{i}", "name": f"Kural {i}"} for i in range(au.MAX_RULES + 5)]
    path = tmp_path / "automations.json"
    content = write(path, {"rules": rules})
    store = au.RuleStore.load(path)
    assert [r.id for r in store.rules] == [f"r{i}" for i in range(au.MAX_RULES)]
    assert_backed_up(store, content, path)
    exact = tmp_path / "exact.json"
    write(exact, {"rules": rules[: au.MAX_RULES]})
    loaded = au.RuleStore.load(exact)
    assert len(loaded.rules) == au.MAX_RULES and not loaded.problem
