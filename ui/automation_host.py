"""Otomasyon motorunu uygulamaya bağlar: dakikalık zamanlayıcı, ışıklara komut gönderen arka uç, bildirimler.

Köprü (`LightBridge`) tek ışıklıdır ve bozulmaz. Bir kuralın hedefi:

* **seçili ışık** ise komut köprünün istemcisinden gider (normal yol: ekran ve enerji kaydı güncellenir);
* **başka bir ışık** ise `blink_light` gibi geçici, ayrı bir `LightClient` ile gider (dinleyicisiz, ana pencere o ışığa
  geçmez). Geçici bağlantı kuralın o ışıktaki işi bitince kapanır. Bluetooth işlemleri sırayla yapılır.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Coroutine
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

import automation as au
import devices as dv
import light_core as lc
from i18n import tr

LOGGER = logging.getLogger("tuya_light.automation")

STATE_WAIT = 2.0  # geçici bağlantıda ışığın durumunu beklemek için en çok (sn)
OPERATION_TIMEOUT = 150.0  # tek bir komutun en çok süresi (bağlanma dahil)
TICK_MS = 30_000
STARTUP_DELAY_MS = 5_000


class LightBackend:
    """`automation.Backend`: seçili ışık için köprü, diğerleri için geçici istemci."""

    def __init__(
        self,
        store: dv.DeviceStore,
        bridge,
        client_factory: Callable[[lc.Config], Any] | None = None,
        state_wait: float = STATE_WAIT,
        operation_timeout: float = OPERATION_TIMEOUT,
    ) -> None:
        self.store, self.bridge = store, bridge
        self._factory = client_factory or (lambda cfg: lc.LightClient(cfg))  # dinleyicisiz: ekrana/enerjiye dokunmaz
        self._state_wait = state_wait
        self._timeout = operation_timeout
        self._clients: dict[str, Any] = {}

    # -- ışık listesi -----------------------------------------------------------------------------

    def light_ids(self) -> list[str]:
        return [d.device_id for d in self.store.devices()]

    def light_name(self, light_id: str) -> str | None:
        cfg = self.store.get(light_id)
        return cfg.name if cfg is not None else None

    def _is_current(self, light_id: str) -> bool:
        cfg = getattr(self.bridge, "cfg", None)
        return cfg is not None and cfg.device_id == light_id and self.store.get(light_id) is not None

    # -- durum / komut --------------------------------------------------------------------------------

    async def state(self, light_id: str) -> lc.LightState | None:
        if self._is_current(light_id):
            return getattr(self.bridge.client, "state", None)
        client = await self._transient(light_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._state_wait
        while client.state.power is None and loop.time() < deadline:
            await asyncio.sleep(0.1)
        return client.state

    async def apply(self, light_id: str, command: au.Command) -> None:
        if self._is_current(light_id):
            await self.release(light_id)  # ışık bu arada seçildiyse geçici bağlantı yolu açsın
            future = self.bridge.execute(lambda client: self._send(client, light_id, command))
            await asyncio.wait_for(asyncio.wrap_future(future), self._timeout)
            return
        client = await self._transient(light_id)
        await asyncio.wait_for(self._send(client, light_id, command), self._timeout)

    async def release(self, light_id: str) -> None:
        client = self._clients.pop(light_id, None)
        if client is not None:
            try:
                await client.close()
            except Exception:  # noqa: BLE001 - kapatma hatası önemsiz
                LOGGER.debug("could not close the temporary connection", exc_info=True)

    async def _transient(self, light_id: str) -> Any:
        client = self._clients.get(light_id)
        if client is None:
            cfg = self.store.get(light_id)
            if cfg is None:
                raise au.PermanentError("unknown_light")
            client = self._clients[light_id] = self._factory(cfg)
        if not client.connected:
            await asyncio.wait_for(client.connect(), self._timeout)
        return client

    @staticmethod
    async def _send(client: Any, light_id: str, command: au.Command) -> None:
        if client.cfg.device_id != light_id:
            raise RuntimeError("the selected light changed")  # yeniden denemede doğru yol seçilir
        cfg = client.cfg
        kind = command.kind
        if kind == "power":
            await client.set_power(bool(command.on))
        elif kind == "brightness":
            await client.set_brightness(command.bright)
        elif kind == "white":
            await client.set_white(command.bright, command.temp)
        elif kind == "colour":
            await client.set_colour_hs(command.hue, command.sat, command.bright)
        elif kind == "scene":
            if command.mode == "white":
                dps = lc.cmd_power(cfg, True) + lc.cmd_white(cfg, command.bright, command.temp)
            else:
                dps = lc.cmd_power(cfg, True) + lc.cmd_colour(cfg, command.hue, command.sat, lc.pct_to_bright(command.bright))
            await client.send(dps)
        else:
            raise ValueError(f"unknown command: {kind!r}")


def _threaded_loop() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=lambda: (asyncio.set_event_loop(loop), loop.run_forever()), name="automation", daemon=True)
    return loop, thread


class AutomationHost(QObject):
    """Dakikalık zamanlayıcı + kural çalıştırıcı. Kural değişiklikleri buradan geçer (`changed` sinyali)."""

    resultReady = Signal(object)  # automation.Result (ana iş parçacığına kuyruklanır)
    changed = Signal()  # kurallar, ayarlar, duraklatma ya da çalışma durumu değişti
    _finished = Signal(str)  # (iç) kural çalıştırması bitti; BLE/otomasyon iş parçacığından ana iş parçacığına

    def __init__(
        self,
        store: au.RuleStore,
        state: au.EngineState,
        backend: au.Backend,
        resolve_preset: Callable[[str], Any | None] | None = None,
        notify: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        zone: au.Zone | None = None,
        submit: Callable[[Coroutine], Any] | None = None,
        tick_ms: int = TICK_MS,
        sleep: Callable[[float], Coroutine] = asyncio.sleep,
        retry_delays: tuple[float, ...] = au.RETRY_DELAYS,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store, self.state, self.backend = store, state, backend
        self._clock = clock
        self._notify = notify
        self.scheduler = au.Scheduler(store, state, zone)
        self.runner = au.Runner(
            backend,
            resolve_preset,
            on_result=self.resultReady.emit,
            sleep=sleep,
            retry_delays=retry_delays,
            describe_error=lc.friendly_error,
        )
        self.last: dict[str, au.Result] = {}  # kural -> en son sonucu (arayüzde durum için)
        self.running: dict[str, int] = {}  # kural -> şu an süren çalıştırma sayısı (yumuşak geçişler dakikalarca sürer)
        self.resultReady.connect(self._on_result)
        self._finished.connect(self._on_finished)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._submit_override = submit
        self._timer = QTimer(self)
        self._timer.setInterval(tick_ms)
        self._timer.timeout.connect(self.tick)

    # -- yaşam döngüsü ----------------------------------------------------------------------------

    def start(self, startup_delay_ms: int = STARTUP_DELAY_MS) -> None:
        if self._submit_override is None and self._loop is None:
            self._loop, self._thread = _threaded_loop()
            self._thread.start()
        self._timer.start()
        QTimer.singleShot(startup_delay_ms, self.run_startup_rules)

    def shutdown(self) -> None:
        self._timer.stop()
        if self._loop is not None and self._thread is not None:
            loop = self._loop

            def stop() -> None:
                for task in asyncio.all_tasks(loop):
                    task.cancel()
                loop.call_later(0.2, loop.stop)

            loop.call_soon_threadsafe(stop)
            self._thread.join(timeout=3)
            self._loop = self._thread = None

    def _submit(self, coroutine: Coroutine) -> bool:
        if self._submit_override is not None:
            self._submit_override(coroutine)
            return True
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(coroutine, self._loop)
            return True
        coroutine.close()  # başlatılmadı: çalıştırılmayacak
        return False

    # -- zamanlama -------------------------------------------------------------------------------------

    def tick(self) -> None:
        """Zamanı gelen kuralları çalıştırır (zamanlayıcı çağırır; testler doğrudan çağırabilir)."""
        for due in self.scheduler.tick(self._clock()):
            self.run(due.rule)

    def run_startup_rules(self) -> None:
        for due in self.scheduler.startup_due(self._clock()):
            self.run(due.rule)

    def run(self, rule: au.Rule) -> None:
        """Kuralı hemen çalıştırır ("Şimdi çalıştır" ve zamanı gelenler); arayüzü bloklamaz."""
        rule_id = rule.id
        self.running[rule_id] = self.running.get(rule_id, 0) + 1

        async def job() -> None:
            try:
                await self.runner.run_rule(rule)
            finally:
                self._finished.emit(rule_id)

        if not self._submit(job()):
            self._on_finished(rule_id, notify=False)
        else:
            self.changed.emit()

    def is_running(self, rule_id: str) -> bool:
        return self.running.get(rule_id, 0) > 0

    def _on_finished(self, rule_id: str, notify: bool = True) -> None:
        count = self.running.get(rule_id, 0) - 1
        if count > 0:
            self.running[rule_id] = count
        else:
            self.running.pop(rule_id, None)
        if notify:
            self.changed.emit()

    # -- kural işlemleri (arayüz buradan geçer) ----------------------------------------------------------

    def add_rule(self, rule: au.Rule) -> au.Rule:
        rule = self.store.add(rule, self._clock())
        self.changed.emit()
        return rule

    def update_rule(self, rule: au.Rule) -> au.Rule:
        rule = self.store.update(rule, self._clock())
        self.changed.emit()
        return rule

    def delete_rule(self, rule_id: str) -> None:
        self.store.delete(rule_id)
        self.state.forget(rule_id)
        self.last.pop(rule_id, None)
        self.changed.emit()

    def set_enabled(self, rule_id: str, enabled: bool) -> None:
        self.store.set_enabled(rule_id, enabled, self._clock())
        self.changed.emit()

    def set_paused(self, paused: bool) -> None:
        if paused == self.scheduler.paused:
            return
        if paused:
            self.scheduler.pause()
        else:
            self.scheduler.resume(self._clock())
        self.changed.emit()

    def set_tolerance(self, minutes: int) -> None:
        self.store.set_tolerance(minutes)
        self.changed.emit()

    # -- sonuçlar ---------------------------------------------------------------------------------------------

    def _on_result(self, result: au.Result) -> None:
        self.last[result.rule_id] = result
        self.changed.emit()
        if result.status == "failed" and self._notify is not None:
            self._notify(failure_message(result))


def failure_message(result: au.Result) -> str:
    reason = result.reason if result.reason in ("unreachable", "unknown_light", "preset_missing") else "other"
    return tr(
        "automation.failed",
        rule=result.rule_name or "—",
        light=result.light_name or "—",
        reason=tr(f"automation.reason_{reason}"),
    )
