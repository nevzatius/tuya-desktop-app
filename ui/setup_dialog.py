"""Işık ekleme sihirbazı: ilk kez kuran kişiyi adım adım yönlendirir.

Adımlar (üstte "Adım n / 4" göstergesi):
  1) hoş geldin  2) Tuya hesabını hazırla  3) Access ID / Secret  4) ışıkları seç ve adlandır
Sonra "Hazırsın" ekranı. İleri düzey: anahtarı elle girme ve veri merkezi seçimi (3. adımda "Gelişmiş").

Access Secret yalnızca bulut çağrısı süresince bellekte durur; hiçbir yere yazılmaz.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QLocale, QRectF, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import cloud_import as ci
import light_core as lc
from i18n import tr

from .icons import app_icon
from .theme import BORDER, DANGER, OK

TUYA_URL = "https://iot.tuya.com"
PAGE_WELCOME, PAGE_ACCOUNT, PAGE_CREDENTIALS, PAGE_LIGHTS, PAGE_MANUAL, PAGE_DONE = range(6)
STEP_PAGES = (PAGE_WELCOME, PAGE_ACCOUNT, PAGE_CREDENTIALS, PAGE_LIGHTS)  # "n / 4" göstergesi bu sayfalarda
ID_PATTERN = re.compile(r"[A-Za-z0-9]{20}")
SECRET_PATTERN = re.compile(r"[A-Za-z0-9]{32}")
SCAN_SECONDS = 6.0
ACCENT = "#8fb4ff"

_LIVE_WORKERS: set[QThread] = set()  # iş parçacıkları pencere kapansa da bitene kadar yaşar


def default_scanner() -> list:
    """Çevredeki Tuya BLE cihazlarını tarar (ayrı iş parçacığında çağrılır)."""
    return asyncio.run(lc.scan_tuya_devices(SCAN_SECONDS))


def signal_text(rssi: int | None) -> str:
    """Sinyal gücünün (dBm) okunur karşılığı."""
    if rssi is None:
        return tr("setup.signal_weak")
    if rssi >= -60:
        return tr("setup.signal_strong")
    return tr("setup.signal_good") if rssi >= -75 else tr("setup.signal_weak")


class _Worker(QThread):
    """`func(*args)`'ı arka planda çalıştırır; sonuç `done`, hata `failed(mesaj, tür)` ile gelir."""

    done = Signal(object)
    failed = Signal(str, str)

    def __init__(self, func: Callable, args: tuple, explain: Callable[[Exception], tuple[str, str]]) -> None:
        super().__init__()
        self._func, self._args, self._explain = func, args, explain
        _LIVE_WORKERS.add(self)
        self.finished.connect(lambda: _LIVE_WORKERS.discard(self))

    def run(self) -> None:
        try:
            result = self._func(*self._args)
        except Exception as exc:  # noqa: BLE001
            message, kind = self._explain(exc)
            self.failed.emit(message, kind)
        else:
            self.done.emit(result)


def _explain_cloud(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, ci.CloudError):
        return str(exc), exc.kind
    return tr("error.unexpected", error=exc), "other"


def _explain_scan(exc: Exception) -> tuple[str, str]:
    return lc.friendly_error(exc), "other"


class StepIndicator(QWidget):
    """Üst kısımdaki küçük ilerleme çubuğu (tamamlanan ve geçerli adımlar vurgulu)."""

    def __init__(self, total: int = 4, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.total, self.current = total, 1
        self.setFixedHeight(8)

    def set_current(self, current: int) -> None:
        self.current = max(1, min(self.total, current))
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gap = 6.0
        width = (self.width() - gap * (self.total - 1)) / self.total
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(self.total):
            p.setBrush(QColor(ACCENT if i < self.current else BORDER))
            p.drawRoundedRect(QRectF(i * (width + gap), 2, width, 4), 2, 2)


class DeviceRow(QFrame):
    """4. adımdaki bir satır: işaret kutusu, ad kutusu ve durum notları."""

    def __init__(self, device: ci.FoundDevice, known: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.device = device
        self._notes: list[str] = []
        self._nearby = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        cfg = device.config
        self.check = QCheckBox(cfg.product_name or cfg.name)
        self.check.setChecked(device.is_light and not known)
        self.name_edit = QLineEdit(cfg.name)
        self.name_edit.setPlaceholderText(tr("setup.name_placeholder"))
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.check)
        lay.addWidget(self.name_edit)
        lay.addWidget(self.status)
        if not device.is_light:
            self._notes.append(tr("setup.not_light"))
        if known:
            self._notes.append(tr("setup.already_added"))
        if device.is_light and not device.is_standard:
            self._notes.append(tr("setup.experimental"))
        self._refresh_status()

    def set_nearby(self, text: str) -> None:
        self._nearby = text
        self._refresh_status()

    def _refresh_status(self) -> None:
        parts = [*self._notes, *([self._nearby] if self._nearby else [])]
        self.status.setText(" · ".join(parts))
        self.status.setVisible(bool(parts))

    @property
    def is_experimental(self) -> bool:
        return self.device.is_light and not self.device.is_standard

    def final_config(self) -> lc.Config:
        cfg = self.device.config
        cfg.name = self.name_edit.text().strip() or cfg.name
        return cfg


class SetupDialog(QDialog):
    def __init__(
        self,
        existing_ids: set[str] | None = None,
        fetcher: Callable | None = None,
        parent: QWidget | None = None,
        scanner: Callable[[], list] | None = None,
        open_url: Callable[[str], Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("setup.title"))
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.resize(520, 680)
        self._existing = existing_ids or set()
        self._fetcher = fetcher or ci.fetch
        self._scanner = scanner or default_scanner
        self._open_url = open_url or (lambda url: QDesktopServices.openUrl(QUrl(url)))
        self._worker: _Worker | None = None
        self._scan_worker: _Worker | None = None
        self._submitted_secret = ""
        self._found: list[ci.FoundDevice] = []
        self._rows: list[DeviceRow] = []
        self._added: list[lc.Config] = []
        self._auto_region = ci.guess_region(QLocale.system().name())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 22)
        outer.setSpacing(12)
        self.step_label = QLabel("")
        self.step_label.setObjectName("muted")
        self.indicator = StepIndicator(len(STEP_PAGES))
        outer.addWidget(self.step_label)
        outer.addWidget(self.indicator)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        for build in (
            self._build_welcome,
            self._build_account,
            self._build_credentials,
            self._build_lights,
            self._build_manual,
            self._build_done,
        ):
            self.stack.addWidget(build())
        self.stack.currentChanged.connect(self._on_page_changed)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)
        # Zaten ışığı olan kullanıcı ışık eklerken tanıtım sayfalarını atlar (Geri ile ulaşır).
        self.stack.setCurrentIndex(PAGE_CREDENTIALS if self._existing else PAGE_WELCOME)
        self._on_page_changed(self.stack.currentIndex())

    # ----------------------------------------------------------- sonuç

    def added_devices(self) -> list[lc.Config]:
        return list(self._added)

    def selected_region(self) -> str:
        return self.region.currentData() or self._auto_region

    # ----------------------------------------------------------- ortak parçalar

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("title")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _text(text: str, name: str = "sub") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    @staticmethod
    def _button(text: str, name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _go(self, page: int) -> Callable[[], None]:
        return lambda: self.stack.setCurrentIndex(page)

    @staticmethod
    def _footer(back: QPushButton | None, primary: QPushButton | None) -> QHBoxLayout:
        row = QHBoxLayout()
        if back is not None:
            row.addWidget(back)
        row.addStretch()
        if primary is not None:
            row.addWidget(primary)
        return row

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        return page, lay

    def _open_tuya_button(self) -> QPushButton:
        button = self._button(tr("setup.open_tuya"), "ghost")
        button.clicked.connect(lambda: self._open_url(TUYA_URL))
        return button

    def _on_page_changed(self, index: int) -> None:
        in_steps = index in STEP_PAGES
        if in_steps:
            number = STEP_PAGES.index(index) + 1
            self.step_label.setText(tr("setup.step_of", current=number, total=len(STEP_PAGES)))
            self.indicator.set_current(number)
        self.step_label.setVisible(in_steps)
        self.indicator.setVisible(in_steps)

    # ----------------------------------------------------------- 1. hoş geldin

    def _build_welcome(self) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._title(tr("setup.welcome_title")))
        lay.addWidget(self._text(tr("setup.welcome_body")))
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.addWidget(self._text(tr("setup.welcome_checklist"), "muted"))
        lay.addWidget(card)
        lay.addStretch()
        self.cancel_button = self._button(tr("setup.cancel"), "ghost")
        self.cancel_button.clicked.connect(self.reject)
        self.start_button = self._button(tr("setup.start"), "primary")
        self.start_button.clicked.connect(self._go(PAGE_ACCOUNT))
        lay.addLayout(self._footer(self.cancel_button, self.start_button))
        return page

    # ----------------------------------------------------------- 2. Tuya hesabı

    def _build_account(self) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._title(tr("setup.account_title")))
        lay.addWidget(self._text(tr("setup.account_intro")))
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(0, 0, 6, 0)
        inner_lay.setSpacing(10)
        self.open_buttons: list[QPushButton] = []
        for key in ("setup.account_step1", "setup.account_step2", "setup.account_step3", "setup.account_step4"):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 12, 14, 12)
            box.setSpacing(8)
            box.addWidget(self._text(tr(key), "sub"))
            button = self._open_tuya_button()
            box.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
            self.open_buttons.append(button)
            inner_lay.addWidget(card)
        inner_lay.addWidget(self._text(tr("setup.account_trouble"), "muted"))
        inner_lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        back = self._button(tr("setup.back"), "ghost")
        back.clicked.connect(self._go(PAGE_WELCOME))
        self.account_next = self._button(tr("setup.account_next"), "primary")
        self.account_next.clicked.connect(self._go(PAGE_CREDENTIALS))
        lay.addLayout(self._footer(back, self.account_next))
        return page

    # ----------------------------------------------------------- 3. bilgiler

    def _build_credentials(self) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._title(tr("setup.cred_title")))
        lay.addWidget(self._text(tr("setup.cred_intro")))

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.access_id = QLineEdit()
        self.access_id.setPlaceholderText(tr("setup.chars_20"))
        self.id_status = QLabel("")
        self.id_status.setObjectName("muted")
        id_row = QHBoxLayout()
        id_row.addWidget(self.access_id, 1)
        id_row.addWidget(self.id_status)
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText(tr("setup.chars_32"))
        self.secret_status = QLabel("")
        self.secret_status.setObjectName("muted")
        self.show_secret = QCheckBox(tr("setup.show"))
        self.show_secret.toggled.connect(
            lambda on: self.secret.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        )
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.secret, 1)
        secret_row.addWidget(self.secret_status)
        form.addRow("Access ID", id_row)
        form.addRow("Access Secret", secret_row)
        form.addRow("", self.show_secret)
        lay.addLayout(form)
        self.access_id.textChanged.connect(lambda _t: self._on_field_changed(self.access_id, self.id_status, ci.ID_LENGTH))
        self.secret.textChanged.connect(lambda _t: self._on_field_changed(self.secret, self.secret_status, ci.SECRET_LENGTH))

        self.paste_note = self._text("", "muted")
        self.paste_note.hide()
        lay.addWidget(self.paste_note)

        self.cloud_message = self._text("", "muted")
        self.cloud_message.hide()
        lay.addWidget(self.cloud_message)
        recover = QHBoxLayout()
        self.retry_button = self._button(tr("setup.retry"), "ghost")
        self.retry_button.clicked.connect(self._start_fetch)
        self.open_tuya_button = self._open_tuya_button()
        recover.addWidget(self.retry_button)
        recover.addWidget(self.open_tuya_button)
        recover.addStretch()
        lay.addLayout(recover)
        self.retry_button.hide()
        self.open_tuya_button.hide()

        # İleri düzey: veri merkezi ve elle anahtar girişi
        self.advanced_toggle = self._button(tr("setup.advanced"), "ghost")
        self.advanced_toggle.setCheckable(True)
        lay.addWidget(self.advanced_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.advanced_box = QFrame()
        self.advanced_box.setObjectName("card")
        adv = QVBoxLayout(self.advanced_box)
        adv.setContentsMargins(14, 12, 14, 12)
        adv.setSpacing(8)
        region_row = QHBoxLayout()
        region_row.addWidget(QLabel(tr("setup.region")))
        self.region = QComboBox()
        self.region.addItem(tr("setup.region_auto"), "")
        for code in ci.REGIONS:
            self.region.addItem(f"{ci.region_label(code)} ({code})", code)
        region_row.addWidget(self.region, 1)
        adv.addLayout(region_row)
        adv.addWidget(self._text(tr("setup.region_hint"), "muted"))
        self.manual_button = self._button(tr("setup.manual_button"), "ghost")
        self.manual_button.clicked.connect(self._go(PAGE_MANUAL))
        adv.addWidget(self.manual_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.advanced_box.hide()
        self.advanced_toggle.toggled.connect(self.advanced_box.setVisible)
        lay.addWidget(self.advanced_box)
        lay.addStretch()

        back = self._button(tr("setup.back"), "ghost")
        back.clicked.connect(self._go(PAGE_ACCOUNT))
        self.find_button = self._button(tr("setup.find"), "primary")
        self.find_button.clicked.connect(self._start_fetch)
        lay.addLayout(self._footer(back, self.find_button))
        return page

    @staticmethod
    def _on_field_changed(edit: QLineEdit, status: QLabel, length: int) -> None:
        """Yapıştırılan boşlukları/görünmez karakterleri atar ve uzunluğu canlı gösterir."""
        cleaned = ci.clean(edit.text())
        if cleaned != edit.text():
            edit.setText(cleaned)  # textChanged yeniden tetiklenir ve durum aşağıda güncellenir
            return
        got = len(cleaned)
        if got == 0:
            status.setText("")
            status.setStyleSheet("")
        elif got == length:
            status.setText(tr("setup.field_ok", got=got, length=length))
            status.setStyleSheet(f"color: {OK};")
        else:
            status.setText(tr("setup.field_status", got=got, length=length))
            status.setStyleSheet("")

    # -- pano algılama --------------------------------------------------------

    def _on_clipboard_changed(self) -> None:
        if self.stack.currentIndex() == PAGE_CREDENTIALS:
            self.apply_clipboard_text(QApplication.clipboard().text())

    def apply_clipboard_text(self, text: str) -> str | None:
        """Panoda tek parça 20 ya da 32 karakterli alfanümerik metin varsa ilgili boş kutuya koyar.

        "id" / "secret" döndürür (hiçbir şey yapılmadıysa None). Yalnızca 3. adımdayken (pano
        değişince) ve ilgili kutu boşken çalışır; kullanıcıya her seferinde "panodan yapıştırıldı" denir.
        """
        parts = (text or "").split()
        if len(parts) != 1:
            return None
        value = ci.clean(parts[0])
        if ID_PATTERN.fullmatch(value) and not self.access_id.text().strip():
            self.access_id.setText(value)
            self._show_paste_note(tr("setup.pasted_id"))
            return "id"
        if SECRET_PATTERN.fullmatch(value) and not self.secret.text().strip():
            self.secret.setText(value)
            self._show_paste_note(tr("setup.pasted_secret"))
            return "secret"
        return None

    def _show_paste_note(self, text: str) -> None:
        self.paste_note.setText(f"<span style='color:{OK}'>✓</span> {text}")
        self.paste_note.show()

    # -- bulut ------------------------------------------------------------------

    def _show_cloud_message(self, text: str, bad: bool = False) -> None:
        self.cloud_message.setText(text)
        self.cloud_message.setStyleSheet(f"color: {DANGER};" if bad else "")
        self.cloud_message.setVisible(bool(text))
        if not bad:
            self.retry_button.hide()
            self.open_tuya_button.hide()

    def _start_fetch(self) -> None:
        if self._worker is not None:
            return
        access_id, secret = ci.clean(self.access_id.text()), ci.clean(self.secret.text())
        problem = ci.validate_credentials(access_id, secret)
        if problem:
            self._show_cloud_message(problem, bad=True)
            return
        self._show_cloud_message(tr("setup.connecting"))
        self.find_button.setEnabled(False)
        self._submitted_secret = secret
        worker = _Worker(self._fetcher, (access_id, secret, self.selected_region()), _explain_cloud)
        worker.done.connect(self._fetch_done)
        worker.failed.connect(self._fetch_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        worker.start()

    def _worker_finished(self) -> None:
        self._worker = None
        self.find_button.setEnabled(True)

    def _fetch_failed(self, message: str, kind: str = "other") -> None:
        self._show_cloud_message(message, bad=True)
        self.retry_button.show()  # çözüm: düzeltip tekrar dene
        self.open_tuya_button.setVisible(kind in ("credentials", "permission", "token", "no_devices"))

    def _fetch_done(self, result: tuple) -> None:
        found, _region = result
        self.secret.clear()  # Secret bellekte gereksiz kalmasın
        clipboard = QApplication.clipboard()
        if self._submitted_secret and clipboard.text().strip() == self._submitted_secret:
            clipboard.clear()  # panoda kalan Secret'i de temizle
        self._submitted_secret = ""
        self.paste_note.hide()
        self._show_cloud_message("")
        self._populate(list(found))
        self.stack.setCurrentIndex(PAGE_LIGHTS)

    # ----------------------------------------------------------- 4. ışıklar

    def _build_lights(self) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._title(tr("setup.lights_title")))
        lay.addWidget(self._text(tr("setup.lights_hint")))
        self.rows_holder = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_holder)
        self.rows_layout.setContentsMargins(0, 0, 6, 0)
        self.rows_layout.setSpacing(10)
        self.rows_layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.rows_holder)
        lay.addWidget(scroll, 1)

        scan_row = QHBoxLayout()
        self.scan_button = self._button(tr("setup.scan"), "ghost")
        self.scan_button.clicked.connect(self._start_scan)
        scan_row.addWidget(self.scan_button)
        scan_row.addStretch()
        lay.addLayout(scan_row)
        self.scan_note = self._text("", "muted")
        self.scan_note.hide()
        lay.addWidget(self.scan_note)
        self.results_note = self._text("", "muted")
        lay.addWidget(self.results_note)

        back = self._button(tr("setup.back"), "ghost")
        back.clicked.connect(self._go(PAGE_CREDENTIALS))
        self.add_button = self._button(tr("setup.add_selected"), "primary")
        self.add_button.clicked.connect(self._add_selected)
        lay.addLayout(self._footer(back, self.add_button))
        return page

    def _populate(self, found: list[ci.FoundDevice]) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        self._found = found
        for dev in found:
            row = DeviceRow(dev, known=dev.config.device_id in self._existing)
            self._rows.append(row)
            self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)
        self.results_note.setText(tr("setup.experimental_note") if any(r.is_experimental for r in self._rows) else "")
        self.scan_note.hide()

    @property
    def rows(self) -> list[DeviceRow]:
        return list(self._rows)

    def _add_selected(self) -> None:
        chosen = [row for row in self._rows if row.check.isChecked()]
        if not chosen:
            self.results_note.setText(tr("setup.pick_one"))
            return
        self._finish([row.final_config() for row in chosen])

    # -- yakın tarama -----------------------------------------------------------

    def _start_scan(self) -> None:
        if self._scan_worker is not None:
            return
        self.scan_button.setEnabled(False)
        self._show_scan_note(tr("setup.scanning"))
        worker = _Worker(self._scanner, (), _explain_scan)
        worker.done.connect(self._scan_done)
        worker.failed.connect(self._scan_failed)
        worker.finished.connect(self._scan_finished)
        self._scan_worker = worker
        worker.start()

    def _scan_finished(self) -> None:
        self._scan_worker = None
        self.scan_button.setEnabled(True)

    def _show_scan_note(self, text: str, bad: bool = False) -> None:
        self.scan_note.setText(text)
        self.scan_note.setStyleSheet(f"color: {DANGER};" if bad else "")
        self.scan_note.setVisible(bool(text))

    def _scan_failed(self, message: str, _kind: str = "other") -> None:
        self._show_scan_note(tr("setup.scan_failed", error=message), bad=True)

    def _scan_done(self, nearby: list) -> None:
        by_uuid = {d.uuid: d for d in nearby if getattr(d, "uuid", None)}
        for row in self._rows:
            if not row.device.is_light:
                continue
            uuid = row.device.config.uuid
            seen = by_uuid.get(uuid) if uuid else None
            if seen is not None:
                row.set_nearby(tr("setup.nearby", signal=signal_text(seen.rssi)))
            else:
                row.set_nearby(tr("setup.not_seen"))
        self._show_scan_note(tr("setup.scan_found", count=len(nearby)) if nearby else tr("setup.scan_none"))

    # ----------------------------------------------------------- elle giriş (ileri düzey)

    def _build_manual(self) -> QWidget:
        page, lay = self._page()
        lay.addWidget(self._title(tr("setup.manual_title")))
        lay.addWidget(self._text(tr("setup.manual_intro")))
        form = QFormLayout()
        form.setSpacing(10)
        self.m_name = QLineEdit()
        self.m_name.setPlaceholderText(tr("setup.manual_name_placeholder"))
        self.m_id = QLineEdit()
        self.m_key = QLineEdit()
        self.m_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.m_uuid = QLineEdit()
        form.addRow(tr("setup.field_name"), self.m_name)
        form.addRow(tr("setup.field_device_id"), self.m_id)
        form.addRow(tr("setup.field_local_key"), self.m_key)
        form.addRow(tr("setup.field_uuid"), self.m_uuid)
        lay.addLayout(form)
        self.manual_message = self._text("", "muted")
        self.manual_message.hide()
        lay.addWidget(self.manual_message)
        lay.addStretch()
        back = self._button(tr("setup.back"), "ghost")
        back.clicked.connect(self._go(PAGE_CREDENTIALS))
        self.manual_add = self._button(tr("setup.add"), "primary")
        self.manual_add.clicked.connect(self._add_manual)
        lay.addLayout(self._footer(back, self.manual_add))
        return page

    def _add_manual(self) -> None:
        device_id, key = ci.clean(self.m_id.text()), self.m_key.text().strip()
        if not device_id or not key:
            self.manual_message.setText(tr("setup.manual_required"))
            self.manual_message.setStyleSheet(f"color: {DANGER};")
            self.manual_message.show()
            return
        self._finish(
            [
                lc.Config(
                    device_id=device_id,
                    local_key=key,
                    uuid=ci.clean(self.m_uuid.text()),
                    name=self.m_name.text().strip() or tr("device.fallback_name"),
                )
            ]
        )

    # ----------------------------------------------------------- başarı

    def _build_done(self) -> QWidget:
        page, lay = self._page()
        lay.addStretch()
        check = QLabel("✓")
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setStyleSheet(f"color: {OK}; font-size: 48px;")
        lay.addWidget(check)
        title = self._title(tr("setup.done_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        self.done_label = self._text("")
        self.done_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.done_label)
        lay.addStretch()
        self.finish_button = self._button(tr("setup.done_button"), "primary")
        self.finish_button.clicked.connect(self.accept)
        lay.addLayout(self._footer(None, self.finish_button))
        return page

    def _finish(self, configs: list[lc.Config]) -> None:
        self._added = configs
        names = ", ".join(f"“{c.name}”" for c in configs)
        self.done_label.setText(tr("setup.done_body", names=names))
        self.stack.setCurrentIndex(PAGE_DONE)

    def reject(self) -> None:
        # "Hazırsın" ekranında pencereyi kapatmak, eklenen ışıkları kaybettirmesin.
        if self.stack.currentIndex() == PAGE_DONE and self._added:
            self.accept()
            return
        super().reject()
