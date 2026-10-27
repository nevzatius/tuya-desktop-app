"""Gizli bilgileri metinlerden temizleme (günlük, hata mesajı, tanılama raporu).

Yerel anahtar, cihaz kimliği, uuid, MAC adresi ve Access ID/Secret hiçbir günlüğe, rapora ya da
ekran görüntüsüne girmemeli. İki katman vardır:
  * bilinen değerler (`secrets`) metinde birebir aranıp maskelenir;
  * değer bilinmese de MAC adresi, GUID ve uzun onaltılık dizi kalıpları maskelenir.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "<hidden>"
MIN_SECRET_LENGTH = 6  # "ab" gibi çok kısa değerleri maskelemek metni bozar

_MAC = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}(?![0-9A-Fa-f])")
_GUID = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}(?![0-9A-Fa-f])")
_LONG_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{12,}(?![0-9A-Za-z])")


def redact(text: object, secrets: Iterable[str] = ()) -> str:
    """`text` içindeki bilinen gizli değerleri ve MAC/GUID/uzun hex kalıplarını maskeler."""
    out = str(text)
    for secret in sorted({s for s in secrets if s and len(s) >= MIN_SECRET_LENGTH}, key=len, reverse=True):
        out = out.replace(secret, MASK)
        # Sürücüler adresi ayraçsız/küçük harfle de yazabilir.
        plain = secret.replace(":", "").replace("-", "")
        if plain != secret and len(plain) >= MIN_SECRET_LENGTH:
            out = re.sub(re.escape(plain), MASK, out, flags=re.IGNORECASE)
    for pattern in (_GUID, _MAC, _LONG_HEX):
        out = pattern.sub(MASK, out)
    return out
