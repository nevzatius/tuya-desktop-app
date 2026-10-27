"""Tanılama raporu: sorun bildirirken GitHub'a yapıştırılacak, gizli bilgi içermeyen özet.

Rapora YALNIZCA şunlar girer: uygulama/işletim sistemi/kütüphane sürümleri, ışık sayısı, her ışığın
kategorisi ve ürün adı, son hata ve günlük satırları. Yerel anahtar, cihaz kimliği, uuid, MAC adresi,
Access ID/Secret ve ışıklara verdiğiniz adlar rapora girmez; son satırlar yazılırken bilinen tüm
değerler ve MAC/GUID/uzun hex kalıpları ayrıca maskelenir (bkz. privacy.py).
Rapor bakımcıların okuması içindir, bu yüzden her zaman İngilizcedir.
"""

from __future__ import annotations

import platform
import sys
from collections import deque
from collections.abc import Iterable
from importlib import metadata

import light_core as lc
import version
from privacy import redact

MAX_ERRORS, MAX_LOG_LINES = 15, 50


class RecentEvents:
    """Son hataları ve günlük satırlarını sınırlı sayıda tutar."""

    def __init__(self) -> None:
        self.errors: deque[str] = deque(maxlen=MAX_ERRORS)
        self.log: deque[str] = deque(maxlen=MAX_LOG_LINES)

    def add_error(self, text: str) -> None:
        if not self.errors or self.errors[-1] != text:  # art arda aynı hatayı tekrarlama
            self.errors.append(text)

    def add_log(self, text: str) -> None:
        self.log.append(text)


def _package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def collect_versions() -> dict[str, str]:
    versions = {
        "App": f"{version.APP_NAME} {version.__version__}",
        "OS": platform.platform(),
        "Python": f"{platform.python_version()} ({platform.architecture()[0]})",
        "bleak": _package_version("bleak"),
        "tuya-ble-sdk": _package_version("tuya-ble-sdk"),
        "tinytuya": _package_version("tinytuya"),
        "frozen": str(bool(getattr(sys, "frozen", False))),
    }
    try:
        import PySide6
        from PySide6.QtCore import qVersion

        versions["PySide6 / Qt"] = f"{PySide6.__version__} / {qVersion()}"
    except Exception:  # noqa: BLE001
        versions["PySide6 / Qt"] = "unknown"
    return versions


def known_secrets(lights: Iterable[lc.Config]) -> list[str]:
    """Rapora hiçbir koşulda girmemesi gereken tüm değerler."""
    secrets: list[str] = []
    for cfg in lights:
        secrets += [cfg.local_key, cfg.device_id, cfg.uuid, cfg.address, cfg.name]
    return [s for s in secrets if s]


def _light_line(index: int, cfg: lc.Config) -> str:
    standard = "standard" if cfg.dps == lc.DEFAULT_DPS else "custom"
    category = cfg.category or "unknown"
    product = cfg.product_name or "unknown"
    return f"  {index}. category={category}, product={product}, dp-map={standard}, colour-type={cfg.colour_type}"


def build_report(
    lights: Iterable[lc.Config],
    events: RecentEvents | None = None,
    *,
    language: str = "",
    language_setting: str = "",
    connected: bool | None = None,
    bluetooth: str = "",
    extra_secrets: Iterable[str] = (),
) -> str:
    lights = list(lights)
    events = events or RecentEvents()
    lines = ["## Diagnostic report", ""]
    lines += [f"- {key}: {value}" for key, value in collect_versions().items()]
    lines.append(f"- Language: {language or 'unknown'} (setting: {language_setting or 'unknown'})")
    lines.append(f"- Connected: {'unknown' if connected is None else 'yes' if connected else 'no'}")
    if bluetooth:
        lines.append(f"- Bluetooth check: {bluetooth}")
    lines.append(f"- Lights: {len(lights)}")
    lines += [_light_line(i, cfg) for i, cfg in enumerate(lights, 1)]
    lines += ["", "### Recent errors (oldest first)"]
    lines += [f"- {e}" for e in events.errors] or ["- none"]
    lines += ["", "### Recent log lines (oldest first)", "```"]
    lines += list(events.log) or ["(empty)"]
    lines += ["```"]
    # Son güvenlik ağı: bilinen tüm gizli değerler ve MAC/GUID/hex kalıpları tüm rapordan maskelenir.
    return redact("\n".join(lines), [*known_secrets(lights), *extra_secrets])
