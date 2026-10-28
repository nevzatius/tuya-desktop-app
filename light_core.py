"""Tuya BLE ışık kontrolü: çekirdek katman (arayüzden bağımsız).

`tuya-ble-sdk` el sıkışmayı (şifreleme, oturum anahtarı) yapar ama sadece
okuma sunar. Bu modül üstüne şunları ekler:

* veri noktası (DP) YAZMA: ışığı açma/kapama, parlaklık, renk sıcaklığı, renk
* oturumu açık tutma (ışık prizden beslenir, pil derdi yok)
* cihazı reklam paketindeki şifreli uuid ile bulma (Windows/macOS/Linux)

Hedef cihaz: Tuya "dj" kategorisi, standart v2 komut seti
(switch_led=20, work_mode=21, bright_value_v2=22, temp_value_v2=23,
colour_data_v2=24). Farklıysa config.json içindeki "dps" ile değiştirilir.
"""

from __future__ import annotations

import asyncio
import colorsys
import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from tuya_ble_sdk import (
    SERVICE_UUID,
    DataPoint,
    DataPointType,
    TuyaBleAuthenticationError,
    TuyaBleClient,
    TuyaBleCommandCode,
    TuyaBleConnectionError,
    TuyaBleCredentials,
    TuyaBleError,
    TuyaBleHandshakeTimeoutError,
    parse_advertisement,
)

from i18n import tr
from privacy import redact

LOGGER = logging.getLogger("tuya_light")

def app_dir() -> Path:
    """config.json'un aranacağı klasör: .exe'nin yanı ya da bu dosyanın klasörü."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "config.json"

# Standart "dj" (ışık) v2 komut setinin DP numaraları.
DEFAULT_DPS: dict[str, int] = {
    "switch_led": 20,
    "work_mode": 21,
    "bright_value_v2": 22,
    "temp_value_v2": 23,
    "colour_data_v2": 24,
}
MODES = ("white", "colour", "scene", "music")

BRIGHT_MIN, BRIGHT_MAX = 10, 1000
TEMP_MIN, TEMP_MAX = 0, 1000

OPEN_TIMEOUT = 45.0
SCAN_TIMEOUT = 15.0


# --------------------------------------------------------------------------
# Yapılandırma
# --------------------------------------------------------------------------


class ConfigError(Exception):
    """config.json eksik ya da bozuk."""


class LightNotFound(Exception):
    """Işık Bluetooth taramasında görünmedi."""


def _watts(value: Any, default: float = 9.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if 0 < number <= 2000 else default


@dataclass
class Config:
    device_id: str
    local_key: str
    uuid: str
    name: str = field(default_factory=lambda: tr("device.default_name"))
    address: str = ""  # en son görülen BLE adresi (sadece bilgi)
    dps: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_DPS))
    colour_type: str = "string"  # colour_data_v2 DP tipi: "string" veya "raw"
    category: str = ""  # Tuya ürün kategorisi ("dj" = ışık)
    product_name: str = ""
    watts: float = 9.0  # ışığın tam parlaklıktaki gücü (enerji tahmini için; kullanıcı ayarlar)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> Config:
        if not path.exists():
            raise ConfigError(tr("error.config_missing", name=path.name))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(tr("error.config_unreadable", name=path.name, error=exc)) from exc
        missing = [k for k in ("device_id", "local_key") if not data.get(k)]
        if missing:
            raise ConfigError(tr("error.config_field", name=path.name, fields=", ".join(missing)))
        dps = dict(DEFAULT_DPS)
        dps.update({k: int(v) for k, v in (data.get("dps") or {}).items()})
        return cls(
            device_id=data["device_id"],
            local_key=data["local_key"],
            uuid=data.get("uuid", ""),
            name=data.get("name") or tr("device.default_name"),
            address=data.get("address", ""),
            dps=dps,
            colour_type=data.get("colour_type", "string"),
            category=data.get("category", ""),
            product_name=data.get("product_name", ""),
            watts=_watts(data.get("watts")),
        )

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        try:  # içinde yerel anahtar var; POSIX'te sahibe kısılır (Windows'ta chmod erişimi daraltmaz)
            os.chmod(path, 0o600)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Veri noktası (DP) kodlama
# --------------------------------------------------------------------------

DPValue = bool | int | str | bytes
DPWrite = tuple[int, DataPointType, DPValue]


def _encode_value(data_type: DataPointType, value: DPValue) -> bytes:
    match data_type:
        case DataPointType.BOOLEAN:
            return b"\x01" if value else b"\x00"
        case DataPointType.VALUE:
            return int(value).to_bytes(4, "big", signed=True)
        case DataPointType.ENUM:
            return int(value).to_bytes(1, "big")
        case DataPointType.STRING:
            return str(value).encode()
        case DataPointType.RAW | DataPointType.BITMAP:
            if isinstance(value, str):
                return value.encode()
            return bytes(value)  # type: ignore[arg-type]
    raise ValueError(f"Unknown DP type: {data_type}")


def encode_data_points(dps: list[DPWrite]) -> bytes:
    """`kimlik | tür | uzunluk | değer` kayıtlarını art arda dizer."""
    out = bytearray()
    for identifier, data_type, value in dps:
        raw = _encode_value(data_type, value)
        if not 0 <= identifier <= 255 or len(raw) > 255:
            raise ValueError(f"DP {identifier} could not be encoded")
        out += bytes([identifier, int(data_type), len(raw)]) + raw
    return bytes(out)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def pct_to_bright(pct: float) -> int:
    """%1..%100 -> 10..1000"""
    pct = clamp(pct, 1, 100)
    return int(round(BRIGHT_MIN + (pct - 1) / 99 * (BRIGHT_MAX - BRIGHT_MIN)))


def bright_to_pct(value: int) -> int:
    return int(round(clamp((value - BRIGHT_MIN) / (BRIGHT_MAX - BRIGHT_MIN) * 99 + 1, 1, 100)))


def pct_to_temp(pct: float) -> int:
    """%0 (sıcak) .. %100 (soğuk) -> 0..1000"""
    return int(round(clamp(pct, 0, 100) * 10))


def temp_to_pct(value: int) -> int:
    return int(round(clamp(value, TEMP_MIN, TEMP_MAX) / 10))


def rgb_to_hs(r: int, g: int, b: int) -> tuple[int, int]:
    """RGB (0-255) -> (H 0-360, S 0-1000)"""
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return int(round(h * 360)) % 361, int(round(s * 1000))


def hsv_string(h: int, s: int, v: int) -> str:
    """colour_data_v2 için 12 haneli onaltılık: HHHHSSSSVVVV."""
    h = int(clamp(h, 0, 360))
    s = int(clamp(s, 0, 1000))
    v = int(clamp(v, 0, 1000))
    return f"{h:04x}{s:04x}{v:04x}"


def parse_hsv_string(value: str | bytes) -> tuple[int, int, int] | None:
    if isinstance(value, bytes):
        try:
            value = value.decode()
        except UnicodeDecodeError:
            return None
    if len(value) != 12:
        return None
    try:
        return int(value[0:4], 16), int(value[4:8], 16), int(value[8:12], 16)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Komut üreticileri (hepsi DP listesi döndürür)
# --------------------------------------------------------------------------


def cmd_power(cfg: Config, on: bool) -> list[DPWrite]:
    return [(cfg.dps["switch_led"], DataPointType.BOOLEAN, on)]


def cmd_brightness(cfg: Config, pct: float) -> list[DPWrite]:
    return [(cfg.dps["bright_value_v2"], DataPointType.VALUE, pct_to_bright(pct))]


def cmd_white(cfg: Config, bright_pct: float, temp_pct: float) -> list[DPWrite]:
    return [
        (cfg.dps["work_mode"], DataPointType.ENUM, MODES.index("white")),
        (cfg.dps["bright_value_v2"], DataPointType.VALUE, pct_to_bright(bright_pct)),
        (cfg.dps["temp_value_v2"], DataPointType.VALUE, pct_to_temp(temp_pct)),
    ]


def cmd_colour(cfg: Config, h: int, s: int, v: int, colour_type: str | None = None) -> list[DPWrite]:
    kind = (colour_type or cfg.colour_type).lower()
    data_type = DataPointType.RAW if kind == "raw" else DataPointType.STRING
    return [
        (cfg.dps["work_mode"], DataPointType.ENUM, MODES.index("colour")),
        (cfg.dps["colour_data_v2"], data_type, hsv_string(h, s, v)),
    ]


# --------------------------------------------------------------------------
# Durum
# --------------------------------------------------------------------------


@dataclass
class LightState:
    power: bool | None = None
    mode: str | None = None
    brightness_pct: int | None = None
    temp_pct: int | None = None
    hue: int | None = None
    sat: int | None = None
    val: int | None = None
    raw: dict[int, Any] = field(default_factory=dict)

    @classmethod
    def from_values(cls, cfg: Config, values: dict[int, Any]) -> LightState:
        st = cls(raw=dict(values))
        dps = cfg.dps
        if isinstance(values.get(dps["switch_led"]), bool):
            st.power = values[dps["switch_led"]]
        mode = values.get(dps["work_mode"])
        if isinstance(mode, int) and 0 <= mode < len(MODES):
            st.mode = MODES[mode]
        bright = values.get(dps["bright_value_v2"])
        if isinstance(bright, int) and not isinstance(bright, bool):
            st.brightness_pct = bright_to_pct(bright)
        temp = values.get(dps["temp_value_v2"])
        if isinstance(temp, int) and not isinstance(temp, bool):
            st.temp_pct = temp_to_pct(temp)
        colour = values.get(dps["colour_data_v2"])
        if isinstance(colour, (str, bytes)):
            hsv = parse_hsv_string(colour)
            if hsv:
                st.hue, st.sat, st.val = hsv
        return st


# --------------------------------------------------------------------------
# Bluetooth: tarama ve oturum
# --------------------------------------------------------------------------


@dataclass
class NearbyDevice:
    address: str
    name: str
    rssi: int | None
    uuid: str | None
    product_id: str | None
    bound: bool
    service_hex: dict[str, str] = field(default_factory=dict)
    manufacturer_hex: dict[int, str] = field(default_factory=dict)
    device: Any = None  # bleak BLEDevice (bağlanmak için)


def _norm_address(address: str) -> str:
    return address.replace("-", ":").upper()


class AdvertisementTracker:
    """Reklam paketlerini cihaz (adres) başına birleştirir.

    Tuya cihazları bilgiyi birkaç pakete bölebilir: ürün kaydı (servis verisi)
    bir pakette, şifreli uuid (üretici verisi) başka pakette gelir. Her paketi
    tek başına çözmeye çalışmak uuid'yi `None` bırakır.
    """

    def __init__(self) -> None:
        self._service: dict[str, dict[str, bytes]] = {}
        self._manufacturer: dict[str, dict[int, bytes]] = {}
        self._devices: dict[str, BLEDevice] = {}
        self._rssi: dict[str, int] = {}
        self._names: dict[str, str] = {}
        self._tuya: set[str] = set()

    def feed(self, device: BLEDevice, adv: Any) -> NearbyDevice | None:
        """Paketi işler; cihaz bir Tuya cihazıysa güncel birleşik bilgisini döndürür."""
        address = device.address
        service = self._service.setdefault(address, {})
        manufacturer = self._manufacturer.setdefault(address, {})
        service.update(adv.service_data or {})
        manufacturer.update(adv.manufacturer_data or {})
        self._devices[address] = device
        if adv.rssi is not None:
            self._rssi[address] = adv.rssi
        name = device.name or adv.local_name
        if name:
            self._names[address] = name
        if SERVICE_UUID in service or SERVICE_UUID in (adv.service_uuids or []):
            self._tuya.add(address)
        if address not in self._tuya:
            return None
        return self.describe(address)

    def describe(self, address: str) -> NearbyDevice:
        service = self._service[address]
        manufacturer = self._manufacturer[address]
        try:
            info = parse_advertisement(service, manufacturer)
            uuid, product_id, bound = info.uuid, info.product_id, info.is_bound
        except TuyaBleError:
            uuid, product_id, bound = None, None, False
        return NearbyDevice(
            address=address,
            name=self._names.get(address, ""),
            rssi=self._rssi.get(address),
            uuid=uuid,
            product_id=product_id,
            bound=bound,
            service_hex={key: value.hex() for key, value in service.items()},
            manufacturer_hex={key: value.hex() for key, value in manufacturer.items()},
            device=self._devices[address],
        )

    def devices(self) -> list[NearbyDevice]:
        return [self.describe(address) for address in self._tuya]


async def scan_tuya_devices(timeout: float = 8.0) -> list[NearbyDevice]:
    """Çevredeki Tuya BLE cihazlarını listeler (hata ayıklama için)."""
    tracker = AdvertisementTracker()

    def on_adv(device: BLEDevice, adv: Any) -> None:
        tracker.feed(device, adv)

    async with BleakScanner(detection_callback=on_adv):
        await asyncio.sleep(timeout)
    return sorted(tracker.devices(), key=lambda d: -(d.rssi or -999))


MAX_GUESSES = 3  # uuid çözülemezse en çok bu kadar aday denenir


async def find_candidates(
    cfg: Config, timeout: float = SCAN_TIMEOUT, patience: float = 5.0
) -> list[BLEDevice]:
    """Işık için bağlanılacak adayları, en olası olan önde olacak şekilde döndürür.

    Kesin eşleşme (uuid ya da adres) varsa tek adaydır. Reklamdan uuid
    çözülemiyorsa (bazı cihazlar/sürücüler eksik paket verir) ve çevrede uuid'si
    bilinen başka Tuya cihazı yoksa, uuid'si çözülemeyen cihazlar sinyal gücüne
    göre sıralanıp denenir (birden çok ışığı olanlar için). Yanlış cihaz el
    sıkışmada güvenle reddedilir; bağlanan katman sıradakini dener.
    """
    loop = asyncio.get_running_loop()
    tracker = AdvertisementTracker()
    found: asyncio.Future[BLEDevice] = loop.create_future()
    wanted_address = _norm_address(cfg.address) if cfg.address else ""
    match_any = not cfg.uuid and not wanted_address

    def on_adv(device: BLEDevice, adv: Any) -> None:
        if found.done():
            return
        info = tracker.feed(device, adv)
        if info is None:
            return
        if (
            match_any
            or (cfg.uuid and info.uuid == cfg.uuid)
            or (wanted_address and _norm_address(info.address) == wanted_address)
        ):
            found.set_result(device)

    start = loop.time()
    async with BleakScanner(detection_callback=on_adv):
        while loop.time() - start < timeout:
            if found.done():
                return [found.result()]
            if loop.time() - start >= patience:
                seen = tracker.devices()
                unidentified = sorted((d for d in seen if d.uuid is None), key=lambda d: -(d.rssi or -999))
                other_known = [d for d in seen if d.uuid is not None and d.uuid != cfg.uuid]
                if unidentified and not other_known:
                    LOGGER.info("uuid could not be resolved; trying %d candidate(s)", len(unidentified[:MAX_GUESSES]))
                    return [d.device for d in unidentified[:MAX_GUESSES]]
            await asyncio.sleep(0.2)
    return [found.result()] if found.done() else []


async def find_device(
    cfg: Config, timeout: float = SCAN_TIMEOUT, patience: float = 5.0
) -> BLEDevice | None:
    """En olası tek adayı döndürür (komut satırı/testler için)."""
    candidates = await find_candidates(cfg, timeout, patience)
    return candidates[0] if candidates else None


class LightSession(TuyaBleClient):
    """Açık kalan oturum: bağlan, el sıkış, komut gönder.

    `TuyaBleClient` her okumada bağlanıp kopar; ışık prizden beslendiği için
    burada bağlantıyı açık tutuyoruz. SDK'nın iç (alt çizgili) metotlarına
    dayanır, bu yüzden requirements.txt sürümü sabitler (tuya-ble-sdk==0.1.3).
    """

    def __init__(
        self,
        device: BLEDevice,
        credentials: TuyaBleCredentials,
        on_data_points: Callable[[list[DataPoint]], None] | None = None,
    ) -> None:
        super().__init__(device, credentials)
        self._listener = on_data_points

    @property
    def connected(self) -> bool:
        client = self._client
        return bool(client is not None and client.is_connected and self._session_key)

    async def open(self) -> None:
        try:
            async with asyncio.timeout(OPEN_TIMEOUT):
                await self._async_connect()
                await self._async_handshake()
        except TimeoutError as exc:
            await self._async_disconnect()
            raise TuyaBleConnectionError(tr("error.timeout")) from exc
        except BaseException:
            await self._async_disconnect()
            raise

    async def close(self) -> None:
        await self._async_disconnect()

    async def request_status(self) -> None:
        """Cihazdan tüm DP'leri ister; yanıtlar dinleyiciye asenkron gelir."""
        await self._async_request(TuyaBleCommandCode.SENDER_DEVICE_STATUS, b"")

    async def send_data_points(self, dps: list[DPWrite]) -> bytes:
        reply = await self._async_request(
            TuyaBleCommandCode.SENDER_DATA_POINTS, encode_data_points(dps)
        )
        return reply.data

    def _publish(self, data_points: list[DataPoint]) -> None:
        # Oturum açık kaldığı için SDK'nın okuma kuyruğunu kullanmıyoruz.
        if self._listener is not None and data_points:
            self._listener(data_points)


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, ConfigError):
        return str(exc)
    if isinstance(exc, LightNotFound):
        return tr("error.not_found")
    if isinstance(exc, TuyaBleAuthenticationError):
        return tr("error.auth_rejected")
    if isinstance(exc, TuyaBleHandshakeTimeoutError):
        return tr("error.handshake")
    if isinstance(exc, (TuyaBleError, BleakError, TimeoutError, OSError)):
        return tr("error.bluetooth", error=redact(exc))
    return tr("error.unexpected", error=redact(repr(exc)))


def error_kind(exc: BaseException) -> str:
    """Arayüzün çözüm önermesi için hata türü: not_found, auth, handshake, bluetooth, config ya da other."""
    if isinstance(exc, ConfigError):
        return "config"
    if isinstance(exc, LightNotFound):
        return "not_found"
    if isinstance(exc, TuyaBleAuthenticationError):
        return "auth"
    if isinstance(exc, TuyaBleHandshakeTimeoutError):
        return "handshake"
    if isinstance(exc, (TuyaBleError, BleakError, TimeoutError, OSError)):
        return "bluetooth"
    return "other"


def classify_bluetooth_error(message: str) -> str:
    """Tarama hatası metninden Bluetooth durumu: "off", "missing" ya da "unknown" (emin değilsek iddia etmeyiz)."""
    low = message.lower()
    if any(word in low for word in ("turned off", "is off", "powered off", "disabled", "radio")):
        return "off"
    if any(word in low for word in ("no bluetooth", "adapter", "no default", "unsupported", "not supported", "not found")):
        return "missing"
    return "unknown"


async def check_bluetooth(duration: float = 0.5) -> str:
    """Bluetooth'u kısa bir taramayla dener: "ok", "off", "missing" ya da "unknown"."""
    try:
        async with BleakScanner(detection_callback=lambda *_: None):
            await asyncio.sleep(duration)
    except BleakError as exc:
        return classify_bluetooth_error(str(exc))
    except Exception:  # noqa: BLE001 - beklenmedik: emin olmadığımız bir şeyi söylemeyiz
        return "unknown"
    return "ok"


class LightClient:
    """Üst düzey ışık kontrolü: bağlantıyı yönetir, komutları sıraya koyar."""

    def __init__(
        self,
        cfg: Config,
        on_state: Callable[[LightState], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.state = LightState()
        self._values: dict[int, Any] = {}
        self._session: LightSession | None = None
        self._lock = asyncio.Lock()
        self._on_state = on_state
        self._on_status = on_status
        self._on_log = on_log

    @property
    def connected(self) -> bool:
        """Şu an açık ve el sıkışması tamamlanmış bir oturum var mı?"""
        return self._session is not None and self._session.connected

    # -- bildirimler -------------------------------------------------------

    def _status(self, text: str) -> None:
        LOGGER.info(text)
        if self._on_status:
            self._on_status(text)

    def _secrets(self) -> tuple[str, ...]:
        cfg = self.cfg
        return (cfg.local_key, cfg.device_id, cfg.uuid, cfg.address)

    def _log(self, text: str) -> None:
        text = redact(text, self._secrets())  # günlüğe anahtar/kimlik/adres girmesin
        LOGGER.debug(text)
        if self._on_log:
            self._on_log(text)

    def _on_dps(self, data_points: list[DataPoint]) -> None:
        for dp in data_points:
            self._values[dp.identifier] = dp.value
            self._log(f"DP {dp.identifier} ({dp.data_type.name}) = {dp.value!r}")
        self.state = LightState.from_values(self.cfg, self._values)
        if self._on_state:
            self._on_state(self.state)

    # -- bağlantı ----------------------------------------------------------

    async def connect(self) -> None:
        async with self._lock:
            await self._connect_locked()

    async def _connect_locked(self) -> None:
        if self._session is not None and self._session.connected:
            return
        await self._drop()
        self._status(tr("status.searching"))
        candidates = await find_candidates(self.cfg)
        if not candidates:
            self._status(tr("status.not_found"))
            raise LightNotFound()
        creds = TuyaBleCredentials(
            uuid=self.cfg.uuid, device_id=self.cfg.device_id, local_key=self.cfg.local_key
        )
        session: LightSession | None = None
        for index, device in enumerate(candidates):
            self._log(f"Found candidate {index + 1} of {len(candidates)}")
            self._status(tr("status.connecting"))
            attempt = LightSession(device, creds, self._on_dps)
            try:
                await attempt.open()
            except (TuyaBleAuthenticationError, TuyaBleHandshakeTimeoutError) as exc:
                if index + 1 < len(candidates):  # başka bir cihaz olabilir: sıradakini dene
                    self._log(f"Candidate {index + 1} is not our light ({exc.__class__.__name__}); trying the next one")
                    continue
                self._status(tr("status.failed"))
                raise
            except BaseException:
                self._status(tr("status.failed"))
                raise
            session = attempt
            self.cfg.address = device.address
            break
        assert session is not None
        self._session = session
        self._status(tr("status.connected"))
        try:
            await session.request_status()
        except TuyaBleError as exc:  # durum okuma zorunlu değil
            self._log(f"Could not request status: {exc}")

    async def _drop(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            try:
                await session.close()
            except Exception:  # noqa: BLE001 - kapatma hatası önemsiz
                LOGGER.debug("close error", exc_info=True)

    async def close(self) -> None:
        async with self._lock:
            await self._drop()
            self._status(tr("status.closed"))

    async def reconnect(self) -> None:
        async with self._lock:
            await self._drop()
            await self._connect_locked()

    # -- komutlar ----------------------------------------------------------

    async def send(self, dps: list[DPWrite]) -> None:
        """Komutu gönderir; bağlantı kopmuşsa bir kez yeniden bağlanıp dener."""
        async with self._lock:
            for attempt in (1, 2):
                try:
                    await self._connect_locked()
                    assert self._session is not None
                    ack = await self._session.send_data_points(dps)
                    self._log(f"Sent {[d[0] for d in dps]}, reply={ack.hex() or '-'}")
                    self._apply_optimistic(dps)
                    return
                except (TuyaBleAuthenticationError, TuyaBleHandshakeTimeoutError, LightNotFound):
                    raise
                except (TuyaBleError, BleakError, TimeoutError, OSError) as exc:
                    self._log(f"Send error (attempt {attempt}): {exc}")
                    await self._drop()
                    if attempt == 2:
                        raise

    def _apply_optimistic(self, dps: list[DPWrite]) -> None:
        """Cihaz geri bildirim göndermese de arayüz güncel kalsın."""
        for identifier, _type, value in dps:
            self._values[identifier] = value
        self.state = LightState.from_values(self.cfg, self._values)
        if self._on_state:
            self._on_state(self.state)

    async def refresh(self) -> None:
        async with self._lock:
            await self._connect_locked()
            assert self._session is not None
            await self._session.request_status()

    async def set_power(self, on: bool) -> None:
        await self.send(cmd_power(self.cfg, on))

    async def set_brightness(self, pct: float) -> None:
        st = self.state
        if st.mode == "colour" and st.hue is not None and st.sat is not None:
            await self.send(cmd_colour(self.cfg, st.hue, st.sat, pct_to_bright(pct)))
        else:
            await self.send(cmd_brightness(self.cfg, pct))

    async def set_white(self, bright_pct: float, temp_pct: float) -> None:
        await self.send(cmd_white(self.cfg, bright_pct, temp_pct))

    async def set_colour_rgb(self, r: int, g: int, b: int, bright_pct: float = 100) -> None:
        h, s = rgb_to_hs(r, g, b)
        await self.send(cmd_colour(self.cfg, h, s, pct_to_bright(bright_pct)))

    async def set_colour_hs(self, hue: int, sat: int, bright_pct: float = 100) -> None:
        """Doğrudan cihazın birimleriyle renk: H 0-360, S 0-1000."""
        await self.send(cmd_colour(self.cfg, hue, sat, pct_to_bright(bright_pct)))


# --------------------------------------------------------------------------
# Yanıp söndürme (hangi ışığın hangisi olduğunu bulmak için)
# --------------------------------------------------------------------------

BLINK_TIMES = 2
BLINK_PAUSE = 0.6
STATE_WAIT = 2.0


async def blink_light(
    cfg: Config,
    times: int = BLINK_TIMES,
    pause: float = BLINK_PAUSE,
    state_wait: float = STATE_WAIT,
    client_factory: Callable[[Config], Any] | None = None,
) -> bool:
    """Işığa bağlanır, kısa süre kapatıp açar (`times` kez) ve eski güç durumuna döndürür.

    Bağlanma `LightClient` ile yapılır: `find_candidates` adayları sinyal gücüne göre dener, doğru yerel
    anahtarla el sıkışan ışık bizimdir. Yalnızca güç aç/kapa değişir; parlaklık ve renk olduğu gibi kalır.
    Başlangıç durumu okunamazsa ışık yanıyormuş varsayılır (karanlıkta bırakılmaz).

    İstemci hiçbir dinleyici olmadan kurulur: yanıp sönme enerji kaydına hiç ulaşmaz, yani geçici durum
    değişikliği tüketim tahminini bozmaz. Başlangıçta yanıyor muydu (bool) döndürür.
    """
    client = (client_factory or LightClient)(cfg)
    was_on = True
    try:
        await client.connect()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + state_wait
        while client.state.power is None and loop.time() < deadline:
            await asyncio.sleep(0.1)
        was_on = client.state.power is not False
        try:
            for _ in range(times):
                await client.set_power(not was_on)
                await asyncio.sleep(pause)
                await client.set_power(was_on)
                await asyncio.sleep(pause)
        except BaseException:
            try:  # yarıda kesilirse ışık söner kalmasın
                await client.set_power(was_on)
            except Exception:  # noqa: BLE001
                LOGGER.debug("could not restore power after a failed blink", exc_info=True)
            raise
        return was_on
    finally:
        await client.close()
