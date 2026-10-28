"""Otomasyon arka ucu (köprü + geçici istemci) ve Qt tarafı (zamanlayıcı, bildirim, duraklatma). Işık gerekmez."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication  # noqa: E402
from tuya_ble_sdk import DataPointType  # noqa: E402

import automation as au  # noqa: E402
import devices as dv  # noqa: E402
import light_core as lc  # noqa: E402
from automation_helpers import FakeBackend, FakeClient, FakeState, FixedZone, Preset, at, make_rule  # noqa: E402
from ui.automation_host import AutomationHost, LightBackend, failure_message  # noqa: E402
from ui.bridge import LightBridge  # noqa: E402

TR = FixedZone(3)
A = lc.Config(device_id="light-a-0123456789", local_key="KeyA#0123456789!", uuid="uuid-a", name="Salon")
B = lc.Config(device_id="light-b-0123456789", local_key="KeyB#0123456789!", uuid="uuid-b", name="Yatak odası")


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def wait_for(condition, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def env(qapp, tmp_path):
    FakeClient.instances = []
    store = dv.DeviceStore(tmp_path / "devices.json")
    store.add(lc.Config(**{**A.__dict__}))
    store.add(lc.Config(**{**B.__dict__}))
    store.select(A.device_id)
    created: dict[str, FakeClient] = {}

    def bridge_factory(cfg, **kwargs):
        created.setdefault(cfg.device_id, FakeClient(cfg, **kwargs))
        return created[cfg.device_id]

    bridge = LightBridge(store.current(), client_factory=bridge_factory, watch_interval=0.05)
    bridge.start(watchdog=False)
    transient: list[FakeClient] = []

    def transient_factory(cfg):
        client = FakeClient(cfg)
        transient.append(client)
        return client

    backend = LightBackend(store, bridge, client_factory=transient_factory, state_wait=0.3, operation_timeout=5)
    yield backend, bridge, created, transient, store
    bridge.shutdown()


def run(coro):
    return asyncio.run(coro)


# =============================== arka uç ===============================


def test_selected_light_commands_go_through_the_bridge_client_not_a_temporary_one(env):
    backend, bridge, created, transient, store = env
    run(backend.apply(A.device_id, au.Command("power", on=True)))
    run(backend.apply(A.device_id, au.Command("brightness", bright=40)))
    run(backend.apply(A.device_id, au.Command("white", bright=60, temp=30)))
    run(backend.apply(A.device_id, au.Command("colour", hue=200, sat=900, bright=50)))
    assert created[A.device_id].calls == [("power", True), ("brightness", 40), ("white", 60, 30), ("colour", 200, 900, 50)]
    assert transient == []


def test_other_light_gets_a_temporary_listenerless_client_and_the_bridge_stays_untouched(env):
    backend, bridge, created, transient, store = env
    run(backend.apply(B.device_id, au.Command("power", on=False)))
    assert len(transient) == 1 and transient[0].cfg.device_id == B.device_id
    assert transient[0].listeners == (None, None, None)  # ekrana ve enerji kaydına karışmaz
    assert ("connect",) in transient[0].calls and ("power", False) in transient[0].calls
    assert bridge.cfg.device_id == A.device_id and created[A.device_id].calls == []  # köprü başka ışığa geçmedi


def test_temporary_connection_is_reused_across_steps_and_closed_on_release(env):
    async def scenario():
        await backend.apply(B.device_id, au.Command("white", bright=10, temp=10))
        await backend.apply(B.device_id, au.Command("white", bright=20, temp=10))
        await backend.release(B.device_id)

    backend, bridge, created, transient, store = env
    run(scenario())
    assert len(transient) == 1
    assert transient[0].calls.count(("connect",)) == 1 and transient[0].calls[-1] == ("close",)


def test_scene_command_is_one_frame_with_power_on(env):
    backend, bridge, created, transient, store = env
    run(backend.apply(B.device_id, au.Command("scene", mode="white", bright=60, temp=30)))
    dps = next(c[1] for c in transient[0].calls if c[0] == "send")
    cfg = store.get(B.device_id)
    assert dps[0] == (cfg.dps["switch_led"], DataPointType.BOOLEAN, True)
    assert (cfg.dps["work_mode"], DataPointType.ENUM, 0) in dps
    run(backend.apply(B.device_id, au.Command("scene", mode="colour", bright=40, hue=100, sat=500)))
    dps = [c[1] for c in transient[0].calls if c[0] == "send"][1]
    assert (cfg.dps["work_mode"], DataPointType.ENUM, 1) in dps and any(d[0] == cfg.dps["colour_data_v2"] for d in dps)


def test_unknown_light_is_a_permanent_error_and_unreachable_light_raises_for_retry(env):
    backend, bridge, created, transient, store = env
    with pytest.raises(au.PermanentError) as err:
        run(backend.apply("silinmiş", au.Command("power", on=True)))
    assert err.value.reason == "unknown_light" and backend.light_name("silinmiş") is None
    assert backend.light_name(A.device_id) == "Salon" and set(backend.light_ids()) == {A.device_id, B.device_id}

    class Unreachable(FakeClient):
        async def connect(self):
            raise lc.LightNotFound()

    backend._factory = Unreachable
    with pytest.raises(lc.LightNotFound):
        run(backend.apply(B.device_id, au.Command("power", on=True)))


def test_state_of_selected_light_comes_from_the_bridge_and_of_others_from_the_temporary_client(env):
    backend, bridge, created, transient, store = env
    created[A.device_id].state = lc.LightState(power=True, mode="white", brightness_pct=70)
    assert run(backend.state(A.device_id)).brightness_pct == 70
    other = run(backend.state(B.device_id))  # bağlanır ve ışığın durumunu okur
    assert other.power is False and other.brightness_pct == 30 and len(transient) == 1


def test_bridge_execute_returns_errors_to_the_caller_without_the_error_banner(env):
    backend, bridge, created, transient, store = env
    seen = []
    bridge.error.connect(seen.append)

    async def boom(client):
        raise lc.LightNotFound()

    future = bridge.execute(boom)
    assert isinstance(future.exception(timeout=3), lc.LightNotFound)
    QApplication.processEvents()
    assert seen == []  # hata bandı gösterilmez; çağıran (otomasyon) yeniden dener/bildirir


def test_command_for_a_light_that_stopped_being_selected_is_rejected_for_a_retry(env):
    backend, bridge, created, transient, store = env

    async def scenario():
        future = bridge.execute(lambda client: backend._send(client, B.device_id, au.Command("power", on=True)))
        return await asyncio.wrap_future(future)

    with pytest.raises(RuntimeError):
        run(scenario())
    assert created[A.device_id].calls == []


def test_end_to_end_runner_on_two_lights_selected_via_bridge_and_other_temporary(env):
    backend, bridge, created, transient, store = env
    runner = au.Runner(backend, sleep=lambda s: asyncio.sleep(0), retry_delays=())
    results = run(runner.run_rule(make_rule("İkisi", au.Trigger(), au.Action(kind="power", power=True), all_lights=True)))
    assert [r.status for r in results] == ["ok", "ok"]
    assert ("power", True) in created[A.device_id].calls and ("power", True) in transient[0].calls
    assert transient[0].calls[-1] == ("close",)  # iş bitince geçici bağlantı kapandı


# =============================== Qt tarafı ===============================


class Inline:
    """Sahte "gönderici": korutini hemen, aynı iş parçacığında çalıştırır."""

    def __call__(self, coroutine):
        asyncio.run(coroutine)


def make_host(tmp_path, backend=None, rules=(), now=None, notify=None, presets=None):
    clock = {"now": now if now is not None else at(TR, 2026, 10, 26, 6, 0)}
    store = au.RuleStore(tmp_path / "automations.json")
    for rule in rules:
        store.add(rule, 0.0)
    state = au.EngineState(tmp_path / "automation_state.json")
    backend = backend or FakeBackend()
    notices: list[str] = [] if notify is None else notify
    host = AutomationHost(
        store,
        state,
        backend,
        resolve_preset=(presets or {}).get,
        notify=notices.append,
        clock=lambda: clock["now"],
        zone=TR,
        submit=Inline(),
        sleep=lambda s: asyncio.sleep(0),
        retry_delays=(0.0, 0.0),
    )
    return host, backend, clock, notices


def test_tick_runs_due_rules_once_and_sends_the_right_command(qapp, tmp_path):
    rule = make_rule("Sabah", au.Trigger(kind="time", time="07:00"), au.Action(kind="power", power=True))
    host, backend, clock, _ = make_host(tmp_path, rules=[rule])
    clock["now"] = at(TR, 2026, 10, 26, 6, 59, 30)
    host.tick()
    assert backend.calls == []
    clock["now"] = at(TR, 2026, 10, 26, 7, 0, 0)
    host.tick()
    host.tick()  # aynı dakikada ikinci tik: tekrar çalışmaz
    assert backend.commands() == [au.Command("power", on=True)]


def test_missed_rule_runs_when_the_app_wakes_up_within_tolerance(qapp, tmp_path):
    rule = make_rule("Sabah", au.Trigger(kind="time", time="07:00"), au.Action(kind="brightness", bright=30))
    host, backend, clock, _ = make_host(tmp_path, rules=[rule])
    clock["now"] = at(TR, 2026, 10, 26, 7, 8, 0)  # uykudan 8 dk sonra
    host.tick()
    assert backend.commands() == [au.Command("brightness", bright=30)]


def test_startup_rules_run_when_the_app_starts(qapp, tmp_path):
    rule = make_rule("Açılış", au.Trigger(kind="startup"), au.Action(kind="preset", preset="movie"))
    presets = {"movie": Preset("colour", 20, hue=28, sat=900)}
    host, backend, clock, _ = make_host(tmp_path, rules=[rule], presets=presets)
    host.run_startup_rules()
    assert backend.commands() == [au.Command("scene", mode="colour", bright=20, temp=0, hue=28, sat=900)]


def test_unreachable_light_gives_a_tray_notification_and_leaves_the_rule_intact(qapp, tmp_path):
    rule = make_rule("Gece", au.Trigger(kind="time", time="23:00"), au.Action(kind="power", power=False))
    host, backend, clock, notices = make_host(tmp_path, backend=FakeBackend(fail={"light-1": -1}), rules=[rule])
    results = []
    host.resultReady.connect(results.append)
    clock["now"] = at(TR, 2026, 10, 26, 23, 0, 0)
    host.tick()
    assert len(notices) == 1 and "Gece" in notices[0] and "Salon" in notices[0] and "ulaşılamadı" in notices[0]
    assert [(r.status, r.reason) for r in results] == [("failed", "unreachable")]
    assert host.last[results[0].rule_id].status == "failed"
    assert host.store.rules[0].enabled  # kural bozulmadı
    backend.fail.clear()
    clock["now"] = at(TR, 2026, 10, 27, 23, 0, 0)  # ertesi gün yine çalışır
    host.tick()
    assert backend.commands() == [au.Command("power", on=False)] and len(notices) == 1


def test_manual_interruption_and_success_do_not_notify(qapp, tmp_path):
    backend = FakeBackend(states={"light-1": FakeState(power=True, mode="white", brightness_pct=10, temp_pct=10)})
    backend.on_apply = lambda be, light, command, count: setattr(be.states[light], "brightness_pct", 99) if count == 2 else None
    rule = make_rule("Geçiş", au.Trigger(), au.Action(kind="white", bright=90, temp=50, fade_min=5))
    host, _, clock, notices = make_host(tmp_path, backend=backend, rules=[rule])
    host.run(host.store.rules[0])
    assert host.last[host.store.rules[0].id].status == "interrupted" and notices == []


def test_failure_message_is_localized_and_covers_every_reason(qapp):
    import i18n

    result = au.Result("r", "Gece", "x", "Salon", "failed", "preset_missing")
    assert "hazır ayar" in failure_message(result)
    for reason in ("unreachable", "unknown_light", "preset_missing", "other", "garip"):
        assert "Gece" in failure_message(au.Result("r", "Gece", "x", "Salon", "failed", reason))
    i18n.set_language("en")
    assert failure_message(au.Result("r", "Night", "x", "Living room", "failed", "unreachable")).startswith("Automation")


def test_pause_blocks_everything_until_resumed(qapp, tmp_path):
    rule = make_rule("Sabah", au.Trigger(kind="time", time="07:00"))
    startup = make_rule("Açılış", au.Trigger(kind="startup"))
    host, backend, clock, _ = make_host(tmp_path, rules=[rule, startup])
    changes = []
    host.changed.connect(lambda: changes.append(1))
    host.set_paused(True)
    host.set_paused(True)  # ikinci çağrı değişiklik sayılmaz
    assert len(changes) == 1 and host.scheduler.paused
    clock["now"] = at(TR, 2026, 10, 26, 7, 0, 0)
    host.tick()
    host.run_startup_rules()
    assert backend.calls == []
    clock["now"] = at(TR, 2026, 10, 26, 7, 1, 0)
    host.set_paused(False)
    host.tick()
    assert backend.calls == []  # duraklatılmışken geçen 07:00 devamda çalışmaz
    clock["now"] = at(TR, 2026, 10, 27, 7, 0, 0)
    host.tick()
    assert len(backend.calls) == 1


def test_run_now_runs_even_disabled_rules_and_does_not_block(qapp, tmp_path):
    rule = make_rule("Kapalı", au.Trigger(kind="time", time="07:00"), au.Action(kind="brightness", bright=20), enabled=False)
    host, backend, clock, _ = make_host(tmp_path, rules=[rule])
    host.run(host.store.rules[0])
    assert backend.commands() == [au.Command("brightness", bright=20)]


def test_rule_changes_emit_changed_and_persist(qapp, tmp_path):
    host, backend, clock, _ = make_host(tmp_path)
    changes = []
    host.changed.connect(lambda: changes.append(1))
    rule = host.add_rule(make_rule("Yeni"))
    rule.name = "Düzenlendi"
    host.update_rule(rule)
    host.set_enabled(rule.id, False)
    host.set_tolerance(20)
    assert len(changes) == 4
    loaded = au.RuleStore.load(tmp_path / "automations.json")
    assert loaded.rules[0].name == "Düzenlendi" and not loaded.rules[0].enabled and loaded.tolerance_min == 20
    host.state.mark(rule.id, "2026-10-26T07:00")
    host.last[rule.id] = au.Result(rule.id, "x", "l", "n", "ok")
    host.delete_rule(rule.id)
    assert host.store.rules == [] and rule.id not in host.state.fired and rule.id not in host.last and len(changes) == 5


def test_not_started_host_with_threaded_default_discards_work_quietly(qapp, tmp_path):
    store = au.RuleStore()
    host = AutomationHost(store, au.EngineState(), FakeBackend())
    host.run(make_rule())  # başlatılmadı: çalıştırılmaz, hata/uyarı yok


def test_started_host_runs_rules_on_its_own_thread_and_shuts_down_cleanly(qapp, tmp_path):
    backend = FakeBackend()
    host = AutomationHost(au.RuleStore(), au.EngineState(), backend, tick_ms=10_000)
    results = []
    host.resultReady.connect(results.append)
    host.start(startup_delay_ms=10_000)
    try:
        host.run(make_rule("İş parçacığı", au.Trigger(), au.Action(kind="power", power=True)))
        assert wait_for(lambda: results)
        assert results[0].status == "ok" and backend.commands() == [au.Command("power", on=True)]
    finally:
        host.shutdown()
    assert host._thread is None
