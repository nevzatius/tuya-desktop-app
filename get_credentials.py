"""Tuya Cloud'dan ışığın bilgilerini alıp config.json'a yazar.

Bluetooth bağlantısı için üç şey gerekir: cihaz kimliği, yerel anahtar (local_key)
ve uuid. Bunları sadece Tuya hesabınız (Cloud projesi) verebilir.

    python get_credentials.py

Access Secret'ı yalnızca bu komut çalışırken bellekte tutulur, hiçbir yere kaydedilmez.
Oluşan config.json içinde yerel anahtar vardır: paylaşmayın.
"""

from __future__ import annotations

import getpass
import re
import sys
from typing import Any

import light_core as lc

DEFAULT_ACCESS_ID = ""
DEFAULT_DEVICE_ID = ""
DEFAULT_REGION = "eu"  # Central Europe. Western Europe için: eu-w


def _result(response: Any) -> dict:
    """tinytuya cloudrequest yanıtından `result` kısmını güvenle al."""
    if isinstance(response, dict) and response.get("success") and isinstance(response.get("result"), dict):
        return response["result"]
    return {}


def fetch_config(cloud: Any, device_id: str) -> lc.Config:
    """`cloud` bir tinytuya.Cloud (ya da aynı arayüze sahip sahte nesne) olabilir."""
    devices = cloud.getdevices() or []
    if isinstance(devices, dict):  # tinytuya hata sözlüğü döndürmüş
        raise RuntimeError(f"Cihaz listesi alınamadı: {devices.get('Error') or devices}")
    entry = next((d for d in devices if d.get("id") == device_id), None)
    if entry is None:
        raise RuntimeError(
            f"{device_id} hesaptaki cihazlar arasında yok. Cloud projesinde Devices > "
            "Link App Account kısmında hesabın bağlı olduğundan emin olun."
        )

    local_key = entry.get("key") or ""
    uuid = entry.get("uuid") or ""
    name = entry.get("name") or "Odamdaki ışık"
    mac = entry.get("mac") or ""

    if not local_key or not uuid:  # yedek: tek cihaz ayrıntısı
        detail = _result(cloud.cloudrequest(f"/v1.0/devices/{device_id}"))
        local_key = local_key or detail.get("local_key", "")
        uuid = uuid or detail.get("uuid", "")
        mac = mac or detail.get("mac", "")
    if not local_key:
        raise RuntimeError("Yerel anahtar (local_key) alınamadı.")

    dps = dict(lc.DEFAULT_DPS)
    specs = _result(cloud.cloudrequest(f"/v1.1/devices/{device_id}/specifications"))
    for item in [*specs.get("functions", []), *specs.get("status", [])]:
        code, dp_id = item.get("code"), item.get("dp_id")
        if code in dps and isinstance(dp_id, int):
            dps[code] = dp_id

    return lc.Config(device_id=device_id, local_key=local_key, uuid=uuid, name=name, address=mac, dps=dps)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    return input(f"{prompt}{suffix}: ").strip() or default


# Access ID 20, Access Secret 32 karakterdir; ikisi de yalnızca harf/rakamdan oluşur.
ID_LENGTH, SECRET_LENGTH = 20, 32
REGIONS = ["eu", "eu-w", "us", "us-e", "in", "sg", "cn"]


def clean(value: str) -> str:
    """Yapıştırmadan kalan boşluk, satır sonu ve kontrol karakterlerini at."""
    return re.sub(r"[^0-9A-Za-z]", "", value)


def connect_cloud(tinytuya: Any, access_id: str, secret: str, region: str, device_id: str) -> tuple[Any, str]:
    """Önce istenen bölgeyi, olmazsa diğerlerini dener.

    Başarılıysa (bulut nesnesi, çalışan bölge), değilse (None, son hata) döndürür.
    """
    last_error = ""
    for candidate in [region] + [r for r in REGIONS if r != region]:
        cloud = tinytuya.Cloud(apiRegion=candidate, apiKey=access_id, apiSecret=secret, apiDeviceID=device_id)
        error = getattr(cloud, "error", None)
        if not error:
            return cloud, candidate
        last_error = str(error)
    return None, last_error


def main() -> int:
    try:
        import tinytuya
    except ImportError:
        print("tinytuya yüklü değil. Önce: pip install -r requirements.txt")
        return 1

    print("Tuya Cloud projenizin bilgileri (iot.tuya.com > Cloud > RoomLight > Overview)")
    access_id = clean(ask("Access ID", DEFAULT_ACCESS_ID))
    region = ask("Bölge", DEFAULT_REGION)
    device_id = clean(ask("Cihaz ID", DEFAULT_DEVICE_ID))
    secret = clean(getpass.getpass("Access Secret (yazarken görünmez; yapıştırıp Enter'a basın): "))

    visible_tried = False
    while True:
        print(f"  Girilen uzunluklar -> Access ID: {len(access_id)} (beklenen {ID_LENGTH}), "
              f"Secret: {len(secret)} (beklenen {SECRET_LENGTH})")
        if len(access_id) == ID_LENGTH and len(secret) == SECRET_LENGTH and device_id:
            cloud, used = connect_cloud(tinytuya, access_id, secret, region, device_id)
            if cloud is not None:
                if used != region:
                    print(f"  Not: bu proje '{used}' bölgesinde çalıştı (girilen: '{region}').")
                break
            print(f"Tuya Cloud bağlantısı başarısız: {used}")
        else:
            print("Girilen değerlerin uzunluğu beklenenden farklı; yapıştırma sırasında karakter kaybolmuş olabilir.")
        if visible_tried:
            return 1
        visible_tried = True
        if ask("Secret'ı bu kez GÖRÜNÜR şekilde girip tekrar denemek ister misiniz? (E/H)", "E").lower() not in ("e", "evet", "y"):
            return 1
        secret = clean(input("Access Secret (görünür): "))

    try:
        cfg = fetch_config(cloud, device_id)
    except RuntimeError as exc:
        print(exc)
        return 1

    cfg.save()
    print(f"\nKaydedildi: {lc.CONFIG_PATH}")
    print(f"  cihaz   : {cfg.name} ({cfg.device_id})")
    print(f"  uuid    : {cfg.uuid or '(alınamadı)'}")
    print(f"  DP'ler  : {cfg.dps}")
    if not cfg.uuid:
        print("\nuuid alınamadı. `python app.py scan` çıktısındaki uuid'yi config.json içine elle yazın.")
    print("\nSonraki adım: python app.py scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
