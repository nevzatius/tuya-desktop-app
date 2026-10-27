"""BLE katmanı (asyncio, ayrı iş parçacığı) ile Qt arasındaki köprü.

* Komutlar arayüzü bloklamaz.
* Kaydırıcı sürüklenirken komutlar birikmez: aynı türdeki bekleyen komutlardan
  yalnızca en son değer gönderilir ("son değer kazanır").
* Bağlantı koparsa arka planda kendiliğinden yeniden bağlanır.
  Işık anahtarı reddederse (yanlış/eski yerel anahtar) boşuna denemez.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from PySide6.QtCore import QObject, Signal
from tuya_ble_sdk import TuyaBleAuthenticationError

import light_core as lc

from .presets import Preset

LOGGER = logging.getLogger("tuya_light.bridge")

Factory = Callable[[], Awaitable[None]]


class LightBridge(QObject):
    state = Signal(object)  # light_core.LightState
    status = Signal(str)  # "Bağlı", "Işık aranıyor…" ...
    error = Signal(str)  # kullanıcıya gösterilecek (çevrilmiş) hata
    problem = Signal(str)  # hatanın türü (light_core.error_kind): arayüz buna göre çözüm önerir; `error`dan sonra gelir
    log = Signal(str)
    connectedChanged = Signal(bool)

    def __init__(
        self,
        cfg: lc.Config,
        client_factory: Callable[..., Any] | None = None,
        parent: QObject | None = None,
        watch_interval: float = 5.0,
    ) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._generation = 0
        self._factory = client_factory or lc.LightClient
        self._client = self._make_client(cfg)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ble", daemon=True)
        self._pending: dict[str, Factory] = {}
        self._running: set[str] = set()
        self._stop = False
        self._fatal = False
        self._connected = False
        self._watch_interval = watch_interval

    def _make_client(self, cfg: lc.Config) -> Any:
        self._generation += 1
        gen = self._generation

        def only_current(emit: Callable[[Any], None]) -> Callable[[Any], None]:
            return lambda value: emit(value) if gen == self._generation else None

        return self._factory(
            cfg,
            on_state=only_current(self.state.emit),
            on_status=only_current(self.status.emit),
            on_log=only_current(self.log.emit),
        )

    @property
    def client(self) -> Any:
        return self._client

    # -- yaşam döngüsü ---------------------------------------------------------

    def start(self, watchdog: bool = True) -> None:
        self._thread.start()
        if watchdog:
            asyncio.run_coroutine_threadsafe(self._watchdog(), self._loop)

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            tasks = asyncio.all_tasks(self._loop)
            for task in tasks:
                task.cancel()
            if tasks:
                self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            self._loop.close()

    def shutdown(self) -> None:
        self._stop = True
        if not self._thread.is_alive():
            return
        try:
            asyncio.run_coroutine_threadsafe(self._client.close(), self._loop).result(timeout=5)
        except Exception:  # noqa: BLE001 - kapanırken hata önemsiz
            LOGGER.debug("close error", exc_info=True)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=3)

    # -- iç yardımcılar --------------------------------------------------------

    def _set_connected(self, ok: bool) -> None:
        if ok != self._connected:
            self._connected = ok
            self.connectedChanged.emit(ok)

    def _report(self, exc: BaseException) -> None:
        if isinstance(exc, TuyaBleAuthenticationError):
            self._fatal = True
        self.error.emit(lc.friendly_error(exc))
        self.problem.emit(lc.error_kind(exc))
        self._set_connected(bool(self._client.connected))

    async def _guard(self, coro: Awaitable[None]) -> None:
        try:
            await coro
            self._set_connected(bool(self._client.connected))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._report(exc)

    def _submit(self, coro: Awaitable[None]) -> None:
        asyncio.run_coroutine_threadsafe(self._guard(coro), self._loop)

    def _latest(self, key: str, factory: Factory) -> None:
        """Aynı `key` için bekleyen komutların yerine bunu koyar (son değer kazanır)."""
        self._loop.call_soon_threadsafe(self._schedule, key, factory)

    def _schedule(self, key: str, factory: Factory) -> None:
        self._pending[key] = factory
        if key not in self._running:
            self._running.add(key)
            self._loop.create_task(self._drain(key))

    async def _drain(self, key: str) -> None:
        try:
            while key in self._pending:
                factory = self._pending.pop(key)
                await self._guard(factory())
        finally:
            self._running.discard(key)

    async def _watchdog(self) -> None:
        delay = self._watch_interval
        while not self._stop:
            ok = bool(self._client.connected)
            self._set_connected(ok)
            if ok:
                delay = self._watch_interval
            elif not self._fatal:
                try:
                    await self._client.connect()
                    self._set_connected(bool(self._client.connected))
                    delay = self._watch_interval
                except asyncio.CancelledError:
                    raise
                except TuyaBleAuthenticationError as exc:
                    self._fatal = True
                    self.error.emit(lc.friendly_error(exc))
                    self.problem.emit(lc.error_kind(exc))
                except Exception as exc:  # noqa: BLE001
                    self.error.emit(lc.friendly_error(exc))
                    self.problem.emit(lc.error_kind(exc))
                    delay = min(delay * 1.6, 45.0)
            await asyncio.sleep(delay)

    # -- arayüzün kullandığı komutlar -----------------------------------------

    def set_power(self, on: bool) -> None:
        self._latest("power", lambda: self._client.set_power(on))

    def set_brightness(self, pct: int) -> None:
        self._latest("light", lambda: self._client.set_brightness(pct))

    def set_white(self, bright_pct: int, temp_pct: int) -> None:
        self._latest("light", lambda: self._client.set_white(bright_pct, temp_pct))

    def set_colour(self, hue: int, sat: int, bright_pct: int) -> None:
        self._latest("light", lambda: self._client.set_colour_hs(hue, sat, bright_pct))

    def apply_scene(self, preset: Preset) -> None:
        """Hazır ayarı tek pakette gönderir: ışığı aç + modu/değerleri ayarla."""
        cfg = self.cfg
        if preset.mode == "white":
            dps = lc.cmd_power(cfg, True) + lc.cmd_white(cfg, preset.bright, preset.temp)
        else:
            dps = lc.cmd_power(cfg, True) + lc.cmd_colour(cfg, preset.hue, preset.sat, lc.pct_to_bright(preset.bright))
        self._latest("light", lambda: self._client.send(dps))

    def execute(self, operation: Callable[[Any], Awaitable[Any]]) -> concurrent.futures.Future:
        """`operation(istemci)`'yi BLE iş parçacığında, seçili ışığın istemcisiyle çalıştırır (otomasyonlar için).

        Sonuç ya da hata çağırana döner; arayüze hata bandı/sinyal göndermez (çağıran yeniden dener ya da bildirir).
        Komut normal yoldan gittiği için enerji kaydı ve ekran durumu da güncellenir.
        """

        async def run() -> Any:
            return await operation(self._client)

        return asyncio.run_coroutine_threadsafe(run(), self._loop)

    def set_device(self, cfg: lc.Config) -> None:
        """Başka bir ışığa geç: eski bağlantıyı kapat, bekleyen komutları at, yenisine bağlan."""
        if self._thread.is_alive():
            asyncio.run_coroutine_threadsafe(self._switch(cfg), self._loop)
        else:  # henüz başlamadıysa doğrudan değiştir
            self.cfg, self._client, self._fatal = cfg, self._make_client(cfg), False

    def release_device(self) -> None:
        """Işık kalmadı: bağlantıyı kapat ve yeniden bağlanmayı durdur."""
        self._fatal = True  # izleyici yeniden denemesin
        self._generation += 1  # eski istemcinin geç olayları gösterilmesin
        self._loop.call_soon_threadsafe(self._pending.clear)
        if self._thread.is_alive():
            self._submit(self._client.close())
        self._set_connected(False)

    async def _switch(self, cfg: lc.Config) -> None:
        old = self._client
        self._pending.clear()
        self.cfg, self._fatal = cfg, False
        self._client = self._make_client(cfg)
        self._set_connected(False)
        try:
            await old.close()
        except Exception:  # noqa: BLE001
            LOGGER.debug("could not close the previous connection", exc_info=True)

    def refresh(self) -> None:
        self._submit(self._client.refresh())

    def reconnect(self) -> None:
        self._fatal = False
        self._submit(self._client.reconnect())
