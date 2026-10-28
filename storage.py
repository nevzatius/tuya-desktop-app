"""Küçük JSON dosyaları için ortak okuma/yazma (Qt'den bağımsız).

* Yazma atomiktir: önce geçici dosyaya yazılır, sonra yerine konur; yarım dosya kalmaz.
* Okuma bozuk dosyada çökmez: dosyanın yedeği alınır (`<ad>.bad-<tarih>`), çağıran boş başlar.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("tuya_light.storage")

# Geçerli JSON ama beklenmeyen biçimde (yanlış tip, aşırı iç içe, dev sayı) veriyi ayrıştırırken çıkabilecek hatalar:
# kayıt tek tek atlanır, uygulama çökmez.
PARSE_ERRORS = (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError)


def write_json_atomic(path: Path, payload: Any, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if private:  # POSIX: yalnızca sahip okur/yazar. Windows'ta chmod sadece salt-okunur bayrağını etkiler (erişimi daraltmaz)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def backup_file(path: Path) -> Path | None:
    """Dosyayı yanına `<ad>.bad-<tarih>` olarak kopyalar; kopyalanamazsa None (çağıran yine de devam eder)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bad-{stamp}")
    counter = 1
    while target.exists():
        target = path.with_name(f"{path.name}.bad-{stamp}-{counter}")
        counter += 1
    try:
        shutil.copy2(path, target)
    except OSError:
        LOGGER.warning("could not back up %s", path.name)
        return None
    return target


def load_json(path: Path) -> tuple[Any, Path | None, bool]:
    """(veri, yedek yolu, bozuk mu).

    Dosya yoksa (None, None, False). Okunamıyor, geçerli JSON değil (ya da kökü `null`) ya da aşırı iç içeyse (RecursionError) yedeği
    alınır ve (None, yedek, True) döner.
    """
    if not path.exists():
        return None, None, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data is None:  # kök `null`: dosyalarımızın hiçbiri bunu beklemez; "dosya yok"tan ayırt edilsin diye bozuk sayılır
            raise ValueError("null root")
        return data, None, False
    except (OSError, ValueError, RecursionError):
        LOGGER.warning("%s is unreadable; keeping a backup and starting empty", path.name)
        return None, backup_file(path), True
