"""README için ekran görüntüleri: Qt offscreen modunda, tamamen ÖRNEK verilerle.

Gerçek ışık, yerel anahtar, cihaz kimliği ya da hesap bilgisi kullanılmaz; tüm değerler burada uydurulmuştur.

    python docs/make_screenshots.py

Çıktı: docs/screenshots/en/*.png ve docs/screenshots/tr/*.png
(home, color, energy, wizard-keys, wizard-lights)
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":  # offscreen eklentisi sistem yazı tiplerini kendiliğinden bulamaz
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QSettings, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import cloud_import as ci  # noqa: E402
import energy as en  # noqa: E402
import i18n  # noqa: E402
import light_core as lc  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.setup_dialog import PAGE_CREDENTIALS, PAGE_LIGHTS, SetupDialog  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

NOW = datetime(2026, 10, 27, 21, 0)
SAMPLE_NAMES = {"en": ("Living room", "Bedroom"), "tr": ("Salon", "Yatak odası")}


class SampleBridge(QObject):
    """MainWindow'un beklediği yüzey; hiçbir şey göndermez."""

    state = Signal(object)
    status = Signal(str)
    error = Signal(str)
    problem = Signal(str)
    log = Signal(str)
    connectedChanged = Signal(bool)

    def __getattr__(self, name):  # set_power, set_white, reconnect, refresh...
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


def sample_usage(log: en.EnergyLog, device: str) -> None:
    """Son 30 güne yayılmış örnek kullanım: akşamları parlak, geceye doğru kısık."""
    for days_ago in range(30, -1, -1):
        day = (NOW - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
        evening = 3.5 + (days_ago % 4) * 0.6  # saat
        start = day + timedelta(hours=18)
        end = min(start + timedelta(hours=evening), NOW)
        if start >= NOW:
            continue
        log.set_watts(device, 9.0, start.timestamp())
        mid = min(start + timedelta(hours=evening * 0.6), end)
        log.set_watts(device, 4.5, mid.timestamp())
        log.stop(device, end.timestamp())


def sample_found(lang: str) -> list[ci.FoundDevice]:
    first, second = SAMPLE_NAMES[lang]
    return [
        ci.FoundDevice(lc.Config(device_id="sample-1", local_key="sample", uuid="sample-1", name=first, product_name="Smart bulb", category="dj"), True, True),
        ci.FoundDevice(lc.Config(device_id="sample-2", local_key="sample", uuid="sample-2", name=second, product_name="Smart bulb", category="dj"), True, True),
    ]


def shoot(app: QApplication, lang: str, out: Path, tmp: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    i18n.set_language(lang)
    i18n.set_currency("USD")
    settings = QSettings(str(tmp / f"{lang}.ini"), QSettings.Format.IniFormat)
    if lang == "en":
        settings.setValue("energy/price_en", 0.20)
        settings.setValue("energy/currency", "USD")
    name = SAMPLE_NAMES[lang][0]
    cfg = lc.Config(device_id="sample-1", local_key="sample", uuid="sample-1", name=name, category="dj", product_name="Smart bulb", watts=9.0)

    log = en.EnergyLog(":memory:", clock=lambda: NOW.timestamp())
    sample_usage(log, cfg.device_id)
    bridge = SampleBridge()
    win = MainWindow(cfg, bridge, settings=settings, use_tray=False, energy_log=log)
    win.energy._clock = lambda: NOW.timestamp()
    win.energy.set_device(cfg.device_id, cfg.watts)
    win.resize(430, 860)
    win.show()
    bridge.status.emit(i18n.tr("status.connected"))

    bridge.state.emit(lc.LightState(power=True, mode="white", brightness_pct=70, temp_pct=30))
    win.power.settle()
    app.processEvents()
    win.grab().save(str(out / "home.png"))

    bridge.state.emit(lc.LightState(power=True, mode="colour", hue=200, sat=900, val=700))
    win.power.settle()
    app.processEvents()
    win.grab().save(str(out / "color.png"))

    win.tab_energy.click()
    app.processEvents()
    win.grab().save(str(out / "energy.png"))
    win.close()
    log.close()

    dialog = SetupDialog(set(), fetcher=lambda *a: ([], "eu"), scanner=lambda: [], open_url=lambda url: None)
    dialog.resize(520, 680)
    dialog.show()
    dialog.stack.setCurrentIndex(PAGE_CREDENTIALS)
    dialog.access_id.setText("A1B2C3D4E5F6G7H8I9J0")  # örnek: gerçek değil
    dialog.secret.setText("x" * 32)
    dialog._show_paste_note(i18n.tr("setup.pasted_id"))
    app.processEvents()
    dialog.grab().save(str(out / "wizard-keys.png"))

    dialog._populate(sample_found(lang))
    dialog.rows[0].set_nearby(i18n.tr("setup.nearby", signal=i18n.tr("setup.signal_strong")))
    dialog.rows[1].set_nearby(i18n.tr("setup.not_seen"))
    dialog.stack.setCurrentIndex(PAGE_LIGHTS)
    app.processEvents()
    dialog.grab().save(str(out / "wizard-lights.png"))
    dialog.close()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory() as tmp:
        for lang in ("en", "tr"):
            shoot(app, lang, ROOT / "docs" / "screenshots" / lang, Path(tmp))
            print(f"{lang}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
