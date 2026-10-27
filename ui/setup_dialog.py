"""Işık ekleme sihirbazı: Tuya Cloud'dan otomatik ya da elle anahtar girişi."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import cloud_import as ci
import light_core as lc
from i18n import tr

from .icons import app_icon

PAGE_START, PAGE_CLOUD, PAGE_RESULTS, PAGE_MANUAL = range(4)

class _FetchWorker(QThread):
    done = Signal(list, str)
    failed = Signal(str)

    def __init__(self, fetcher: Callable, access_id: str, secret: str, region: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._args = (fetcher, access_id, secret, region)

    def run(self) -> None:
        fetcher, access_id, secret, region = self._args
        try:
            found, used = fetcher(access_id, secret, region)
        except ci.CloudError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(tr("error.unexpected", error=exc))
        else:
            self.done.emit(found, used)


class SetupDialog(QDialog):
    def __init__(self, existing_ids: set[str] | None = None, fetcher: Callable | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("setup.title"))
        self.setWindowIcon(app_icon())
        self.setModal(True)
        self.resize(480, 600)
        self._existing = existing_ids or set()
        self._fetcher = fetcher or ci.fetch
        self._worker: _FetchWorker | None = None
        self._found: list[ci.FoundDevice] = []
        self._added: list[lc.Config] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(14)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(self._build_start())
        self.stack.addWidget(self._build_cloud())
        self.stack.addWidget(self._build_results())
        self.stack.addWidget(self._build_manual())

    # ----------------------------------------------------------- sonuç

    def added_devices(self) -> list[lc.Config]:
        return list(self._added)

    # ----------------------------------------------------------- sayfalar

    @staticmethod
    def _title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("title")
        return label

    @staticmethod
    def _text(text: str, name: str = "sub") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def _build_start(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addWidget(self._title(tr("setup.title")))
        lay.addWidget(
            self._text(tr("setup.intro"))
        )
        self.cloud_button = QPushButton(tr("setup.cloud_button"))
        self.cloud_button.setObjectName("primary")
        self.manual_button = QPushButton(tr("setup.manual_button"))
        self.manual_button.setObjectName("ghost")
        self.cloud_button.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_CLOUD))
        self.manual_button.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_MANUAL))
        lay.addSpacing(6)
        lay.addWidget(self.cloud_button)
        lay.addWidget(self.manual_button)
        lay.addStretch()
        cancel = QPushButton(tr("setup.cancel"))
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        lay.addWidget(cancel, 0, Qt.AlignmentFlag.AlignRight)
        return page

    def _build_cloud(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self._title(tr("setup.cloud_title")))
        self.help_toggle = QPushButton(tr("setup.how"))
        self.help_toggle.setObjectName("ghost")
        self.help_toggle.setCheckable(True)
        lay.addWidget(self.help_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.help_box = QFrame()
        self.help_box.setObjectName("card")
        hb = QVBoxLayout(self.help_box)
        hb.setContentsMargins(14, 12, 14, 12)
        hb.addWidget(self._text(tr("setup.cloud_help"), "muted"))
        self.help_box.hide()
        self.help_toggle.toggled.connect(self.help_box.setVisible)
        lay.addWidget(self.help_box)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.access_id = QLineEdit()
        self.access_id.setPlaceholderText(tr("setup.chars_20"))
        self.secret = QLineEdit()
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText(tr("setup.chars_32"))
        self.show_secret = QCheckBox(tr("setup.show"))
        self.show_secret.toggled.connect(
            lambda on: self.secret.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        )
        secret_row = QHBoxLayout()
        secret_row.addWidget(self.secret)
        secret_row.addWidget(self.show_secret)
        self.region = QComboBox()
        for code in ci.REGIONS:
            self.region.addItem(f"{ci.region_label(code)} ({code})", code)
        form.addRow("Access ID", self.access_id)
        form.addRow("Access Secret", secret_row)
        form.addRow(tr("setup.region"), self.region)
        lay.addLayout(form)

        self.cloud_message = self._text("", "muted")
        self.cloud_message.hide()
        lay.addWidget(self.cloud_message)
        lay.addStretch()

        row = QHBoxLayout()
        back = QPushButton(tr("setup.back"))
        back.setObjectName("ghost")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_START))
        self.find_button = QPushButton(tr("setup.find"))
        self.find_button.setObjectName("primary")
        self.find_button.clicked.connect(self._start_fetch)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(self.find_button)
        lay.addLayout(row)
        return page

    def _build_results(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self._title(tr("setup.results_title")))
        lay.addWidget(self._text(tr("setup.results_hint")))
        self.device_list = QListWidget()
        lay.addWidget(self.device_list, 1)
        self.results_note = self._text("", "muted")
        lay.addWidget(self.results_note)
        row = QHBoxLayout()
        back = QPushButton(tr("setup.back"))
        back.setObjectName("ghost")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_CLOUD))
        self.add_button = QPushButton(tr("setup.add_selected"))
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._add_selected)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(self.add_button)
        lay.addLayout(row)
        return page

    def _build_manual(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self._title(tr("setup.manual_title")))
        lay.addWidget(self._text(tr("setup.manual_intro")))
        form = QFormLayout()
        form.setSpacing(10)
        self.m_name = QLineEdit()
        self.m_name.setPlaceholderText(tr("setup.name_placeholder"))
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
        row = QHBoxLayout()
        back = QPushButton(tr("setup.back"))
        back.setObjectName("ghost")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_START))
        self.manual_add = QPushButton(tr("setup.add"))
        self.manual_add.setObjectName("primary")
        self.manual_add.clicked.connect(self._add_manual)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(self.manual_add)
        lay.addLayout(row)
        return page

    # ----------------------------------------------------------- bulut

    def _show_cloud_message(self, text: str, bad: bool = False) -> None:
        self.cloud_message.setText(text)
        self.cloud_message.setStyleSheet("color: #ff9a9a;" if bad else "")
        self.cloud_message.setVisible(bool(text))

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
        worker = _FetchWorker(self._fetcher, access_id, secret, self.region.currentData(), self)
        worker.done.connect(self._fetch_done)
        worker.failed.connect(self._fetch_failed)
        worker.finished.connect(self._worker_finished)
        self._worker = worker
        worker.start()

    def _worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        self._worker = None
        self.find_button.setEnabled(True)

    def _fetch_failed(self, message: str) -> None:
        self._show_cloud_message(message, bad=True)

    def _fetch_done(self, found: list, region: str) -> None:
        self.secret.clear()  # Secret bellekte gereksiz kalmasın
        self._show_cloud_message("")
        self._found = list(found)
        self.device_list.clear()
        has_non_standard = False
        for dev in self._found:
            item = QListWidgetItem(dev.label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            known = dev.config.device_id in self._existing
            if dev.is_light:
                item.setCheckState(Qt.CheckState.Unchecked if known else Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setText(f"{dev.label}  {tr('setup.not_light')}")
            if known:
                item.setText(f"{item.text()}  {tr('setup.already_added')}")
            if dev.is_light and not dev.is_standard:
                has_non_standard = True
                item.setText(f"{item.text()}  {tr('setup.experimental')}")
            item.setData(Qt.ItemDataRole.UserRole, dev.config.device_id)
            self.device_list.addItem(item)
        note = ""
        if has_non_standard:
            note = tr("setup.experimental_note")
        self.results_note.setText(note)
        self.stack.setCurrentIndex(PAGE_RESULTS)

    def _add_selected(self) -> None:
        chosen = {
            self.device_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.device_list.count())
            if self.device_list.item(i).checkState() == Qt.CheckState.Checked
        }
        self._added = [d.config for d in self._found if d.config.device_id in chosen]
        if not self._added:
            self.results_note.setText(tr("setup.pick_one"))
            return
        self.accept()

    # ----------------------------------------------------------- elle

    def _add_manual(self) -> None:
        device_id, key = ci.clean(self.m_id.text()), self.m_key.text().strip()
        if not device_id or not key:
            self.manual_message.setText(tr("setup.manual_required"))
            self.manual_message.setStyleSheet("color: #ff9a9a;")
            self.manual_message.show()
            return
        self._added = [
            lc.Config(
                device_id=device_id,
                local_key=key,
                uuid=ci.clean(self.m_uuid.text()),
                name=self.m_name.text().strip() or tr("device.fallback_name"),
            )
        ]
        self.accept()

    def reject(self) -> None:
        if self._worker is not None:
            self._worker.wait(3000)
        super().reject()
