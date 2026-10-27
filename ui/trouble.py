"""Sorun giderici kartı: "ışık bulunamadı" için olası nedenler, her birinin çözümü ve "Tekrar dene"."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from i18n import tr

from .theme import DANGER, MUTED, OK, WARN

BLUETOOTH_SETTINGS_URL = "ms-settings:bluetooth"


class TroubleshootCard(QFrame):
    retryRequested = Signal()
    recheckRequested = Signal()
    copyReportRequested = Signal()
    openBluetoothSettings = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)
        title = QLabel(tr("trouble.title"))
        title.setObjectName("title")
        title.setWordWrap(True)
        lay.addWidget(title)
        lay.addWidget(self._label(tr("trouble.intro"), "sub"))

        # 1) Bluetooth: gerçekten denetlenir
        self.bluetooth_label = self._label("", "sub")
        lay.addWidget(self.bluetooth_label)
        bt_row = QHBoxLayout()
        self.recheck_button = self._button(tr("trouble.recheck"), "ghost")
        self.recheck_button.clicked.connect(self.recheckRequested)
        self.settings_button = self._button(tr("trouble.open_bt"), "ghost")
        self.settings_button.clicked.connect(self.openBluetoothSettings)
        bt_row.addWidget(self.recheck_button)
        bt_row.addWidget(self.settings_button)
        bt_row.addStretch()
        lay.addLayout(bt_row)

        # 2-4) Denetlenemeyen nedenler: kullanıcı kontrol eder
        for index, key in enumerate(("phone", "far", "other"), 2):
            lay.addWidget(self._label(f"<b>{index}. {tr(f'trouble.{key}_title')}</b><br>{tr(f'trouble.{key}_fix')}", "sub"))

        buttons = QHBoxLayout()
        self.retry_button = self._button(tr("trouble.retry"), "primary")
        self.retry_button.clicked.connect(self.retryRequested)
        self.report_button = self._button(tr("trouble.copy_report"), "ghost")
        self.report_button.clicked.connect(self.copyReportRequested)
        buttons.addWidget(self.retry_button)
        buttons.addWidget(self.report_button)
        buttons.addStretch()
        lay.addLayout(buttons)
        lay.addWidget(self._label(tr("common.unverified"), "muted"))
        self.set_bluetooth_state("checking")

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    @staticmethod
    def _button(text: str, name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def set_bluetooth_state(self, state: str) -> None:
        """state: "checking", "ok", "off", "missing" ya da "unknown"."""
        colour, mark = {"ok": (OK, "✓"), "off": (DANGER, "✗"), "missing": (DANGER, "✗"), "unknown": (WARN, "?")}.get(
            state, (MUTED, "…")
        )
        text = tr(f"trouble.bt_{state}") if state in ("checking", "ok", "off", "missing", "unknown") else ""
        fix = tr(f"trouble.bt_{state}_fix") if state in ("off", "missing") else ""
        self.bluetooth_state = state
        self.bluetooth_label.setText(
            f"<b>1. {tr('trouble.bt_title')}</b><br><span style='color:{colour}'>{mark}</span> {text}" + (f"<br>{fix}" if fix else "")
        )
        self.settings_button.setVisible(state in ("off", "missing", "unknown"))
        self.recheck_button.setEnabled(state != "checking")
