"""Tuya Cloud projesinden (kullanıcının kendi hesabı) ışıkları ve anahtarlarını çeker.

Arayüzden bağımsızdır; `tinytuya.Cloud` ya da aynı arayüzlü sahte nesneyle çalışır.
Access Secret yalnızca bu çağrı süresince bellekte durur, hiçbir yere yazılmaz.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import light_core as lc
from i18n import tr

REGIONS = ("eu", "eu-w", "us", "us-e", "in", "sg", "cn")  # Tuya veri merkezi kodları
ID_LENGTH, SECRET_LENGTH = 20, 32

# Tuya ışık kategorileri. Yalnızca "dj" bu uygulamanın DP haritasıyla birebir uyumludur.
LIGHT_CATEGORIES = {"dj", "dd", "xdd", "fwd", "dc", "tgq", "tyndj", "fsd"}


def region_label(code: str) -> str:
    return tr(f"region.{code}")


class CloudError(Exception):
    """Kullanıcıya gösterilebilir (çevrilmiş) bulut hatası.

    `kind` arayüzün çözüm önermesi içindir: "credentials", "permission", "token",
    "network", "no_devices", "validation" ya da "other".
    """

    def __init__(self, message: str, kind: str = "other") -> None:
        super().__init__(message)
        self.kind = kind


# Sistem bölgesinden (ör. "tr_TR") varsayılan veri merkezi tahmini. Yanlışsa connect() diğerlerini dener.
_REGION_BY_COUNTRY = {
    "US": "us", "CA": "us", "MX": "us", "BR": "us", "AR": "us", "CL": "us", "CO": "us",
    "IN": "in",
    "CN": "cn",
    "SG": "sg", "JP": "sg", "KR": "sg", "AU": "sg", "NZ": "sg", "ID": "sg", "MY": "sg", "TH": "sg", "VN": "sg", "PH": "sg",
}


def guess_region(locale_name: str | None) -> str:
    country = (locale_name or "").replace("-", "_").split("_")[-1].upper()
    return _REGION_BY_COUNTRY.get(country, "eu")


@dataclass
class FoundDevice:
    config: lc.Config
    is_light: bool
    is_standard: bool  # kategori "dj": DP haritası doğrulanmış tip

    @property
    def label(self) -> str:
        extra = f" · {self.config.product_name}" if self.config.product_name else ""
        return f"{self.config.name}{extra}"


def clean(value: str) -> str:
    """Yapıştırmadan gelen görünmez karakterleri ve boşlukları at."""
    return re.sub(r"[\s​‌‍﻿ ]+", "", value or "")


def validate_credentials(access_id: str, secret: str) -> str | None:
    """Sorun varsa kullanıcıya gösterilecek açıklama, yoksa None."""
    if len(access_id) != ID_LENGTH:
        return tr("cloud.id_length", length=ID_LENGTH, got=len(access_id))
    if len(secret) != SECRET_LENGTH:
        return tr("cloud.secret_length", length=SECRET_LENGTH, got=len(secret))
    return None


def connect(access_id: str, secret: str, region: str, cloud_factory: Callable[..., Any] | None = None) -> tuple[Any, str]:
    """Önce seçilen bölgeyi, olmazsa diğerlerini dener. (bulut nesnesi, çalışan bölge) döndürür."""
    if cloud_factory is None:
        try:
            import tinytuya
        except ImportError as exc:
            raise CloudError(tr("cloud.no_tinytuya"), "other") from exc
        cloud_factory = tinytuya.Cloud
    last = ""
    for candidate in [region] + [r for r in REGIONS if r != region]:
        try:
            cloud = cloud_factory(apiRegion=candidate, apiKey=access_id, apiSecret=secret)
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
            continue
        error = getattr(cloud, "error", None)
        if not error:
            return cloud, candidate
        last = str(error)
    raise CloudError(_explain(last), classify(last))


def classify(raw: str) -> str:
    """Tuya Cloud hata metninden hata türü."""
    low = raw.lower()
    if "sign invalid" in low or "911" in low:
        return "credentials"
    if "permission" in low or "1106" in low:
        return "permission"
    if "token" in low:
        return "token"
    if any(word in low for word in ("timed out", "timeout", "connection", "resolve", "unreachable", "network")):
        return "network"
    return "other"


def _explain(raw: str) -> str:
    kind = classify(raw)
    if kind == "credentials":
        return tr("cloud.sign_invalid")
    if kind == "permission":
        return tr("cloud.permission")
    if kind == "token":
        return tr("cloud.token")
    if kind == "network":
        return tr("cloud.network")
    return tr("cloud.failed", error=raw or tr("cloud.unknown_error"))


def _result(response: Any) -> dict:
    if isinstance(response, dict) and response.get("success") and isinstance(response.get("result"), dict):
        return response["result"]
    return {}


def _dps_for(cloud: Any, device_id: str) -> dict[str, int]:
    dps = dict(lc.DEFAULT_DPS)
    try:
        specs = _result(cloud.cloudrequest(f"/v1.1/devices/{device_id}/specifications"))
    except Exception:  # noqa: BLE001 - özellik alınamazsa standart harita kullanılır
        return dps
    for item in [*specs.get("functions", []), *specs.get("status", [])]:
        code, dp_id = item.get("code"), item.get("dp_id")
        if code in dps and isinstance(dp_id, int):
            dps[code] = dp_id
    return dps


def list_devices(cloud: Any) -> list[FoundDevice]:
    """Hesaba bağlı tüm cihazları döndürür (ışıklar önce)."""
    raw = cloud.getdevices()
    if isinstance(raw, dict):
        message = raw.get("Error") or raw.get("Payload") or raw
        raise CloudError(tr("cloud.list_failed", error=message), classify(str(message)))
    found: list[FoundDevice] = []
    for item in raw or []:
        device_id, key = item.get("id", ""), item.get("key") or item.get("local_key") or ""
        if not device_id or not key:
            continue
        category = item.get("category", "")
        cfg = lc.Config(
            device_id=device_id,
            local_key=key,
            uuid=item.get("uuid", ""),
            name=item.get("name") or item.get("product_name") or tr("device.fallback_name"),
            address=item.get("mac", ""),
            category=category,
            product_name=item.get("product_name", ""),
        )
        found.append(FoundDevice(cfg, category in LIGHT_CATEGORIES, category == "dj"))
    if not found:
        raise CloudError(tr("cloud.no_devices"), "no_devices")
    found.sort(key=lambda d: (not d.is_light, d.config.name.lower()))
    for d in found:
        if d.is_light:  # DP numaralarını cihazın gerçek özelliklerinden oku
            d.config.dps = _dps_for(cloud, d.config.device_id)
    return found


def fetch(access_id: str, secret: str, region: str, cloud_factory: Callable[..., Any] | None = None) -> tuple[list[FoundDevice], str]:
    access_id, secret = clean(access_id), clean(secret)
    problem = validate_credentials(access_id, secret)
    if problem:
        raise CloudError(problem, "validation")
    cloud, used = connect(access_id, secret, region, cloud_factory)
    return list_devices(cloud), used
