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

REGIONS = {
    "eu": "Orta Avrupa (Türkiye için genelde bu)",
    "eu-w": "Batı Avrupa",
    "us": "Batı ABD",
    "us-e": "Doğu ABD",
    "in": "Hindistan",
    "sg": "Singapur",
    "cn": "Çin",
}
ID_LENGTH, SECRET_LENGTH = 20, 32

# Tuya ışık kategorileri. Yalnızca "dj" bu uygulamanın DP haritasıyla birebir uyumludur.
LIGHT_CATEGORIES = {"dj", "dd", "xdd", "fwd", "dc", "tgq", "tyndj", "fsd"}


class CloudError(Exception):
    """Kullanıcıya gösterilebilir Türkçe bulut hatası."""


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
    """Sorun varsa Türkçe açıklama, yoksa None."""
    if len(access_id) != ID_LENGTH:
        return f"Access ID {ID_LENGTH} karakter olmalı (şu an {len(access_id)})."
    if len(secret) != SECRET_LENGTH:
        return f"Access Secret {SECRET_LENGTH} karakter olmalı (şu an {len(secret)}). Yapıştırırken karakter kaybolmuş olabilir."
    return None


def connect(access_id: str, secret: str, region: str, cloud_factory: Callable[..., Any] | None = None) -> tuple[Any, str]:
    """Önce seçilen bölgeyi, olmazsa diğerlerini dener. (bulut nesnesi, çalışan bölge) döndürür."""
    if cloud_factory is None:
        try:
            import tinytuya
        except ImportError as exc:
            raise CloudError("tinytuya yüklü değil. kur.ps1'i yeniden çalıştırın.") from exc
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
    raise CloudError(_explain(last))


def _explain(raw: str) -> str:
    low = raw.lower()
    if "sign invalid" in low or "911" in low:
        return "Access ID veya Secret yanlış (ya da bu bölgeye ait değil). Değerleri iot.tuya.com'dan yeniden kopyalayın."
    if "permission" in low or "1106" in low:
        return "Proje bu işlem için yetkili değil. Cloud projesinde 'Smart Home' API paketlerinin ekli olduğundan emin olun."
    if "token" in low:
        return "Tuya Cloud'dan oturum alınamadı. Bilgileri ve internet bağlantısını kontrol edin."
    return f"Tuya Cloud bağlantısı başarısız: {raw or 'bilinmeyen hata'}"


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
        raise CloudError(f"Cihaz listesi alınamadı: {message}")
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
            name=item.get("name") or item.get("product_name") or "Işık",
            address=item.get("mac", ""),
            category=category,
            product_name=item.get("product_name", ""),
        )
        found.append(FoundDevice(cfg, category in LIGHT_CATEGORIES, category == "dj"))
    if not found:
        raise CloudError(
            "Bu projeye bağlı cihaz bulunamadı. Cloud projesinde Devices → Link App Account bölümünden "
            "Smart Life hesabınızı QR ile bağlayın."
        )
    found.sort(key=lambda d: (not d.is_light, d.config.name.lower()))
    for d in found:
        if d.is_light:  # DP numaralarını cihazın gerçek özelliklerinden oku
            d.config.dps = _dps_for(cloud, d.config.device_id)
    return found


def fetch(access_id: str, secret: str, region: str, cloud_factory: Callable[..., Any] | None = None) -> tuple[list[FoundDevice], str]:
    access_id, secret = clean(access_id), clean(secret)
    problem = validate_credentials(access_id, secret)
    if problem:
        raise CloudError(problem)
    cloud, used = connect(access_id, secret, region, cloud_factory)
    return list_devices(cloud), used
