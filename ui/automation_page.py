"""Otomasyon sekmesi: kural listesi, ekle/düzenle/sil, aç/kapa, "Şimdi çalıştır" ve sınırların kısa özeti."""

from __future__ import annotations

import time
from collections.abc import Callable

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget

import automation as au
import i18n
from i18n import tr
from version import APP_NAME

from .automation_host import AutomationHost
from .automation_text import error_text, last_text, next_text, summary_text, targets_text
from .presets import PresetStore
from .rule_dialog import UNSET_LAT, UNSET_LON, RuleDialog
from .widgets import ToggleSwitch


def example_rules() -> dict[str, au.Rule]:
    """Boş durumdaki örnekler (kaydedilmez; pencerede doldurulmuş açılır). Koordinat bilinmediği için kullanıcıdan istenir."""
    sunset = au.Rule(
        name=tr("automation.example_sunset_name"),
        trigger=au.Trigger(kind="sun", event="sunset", offset=0, lat=UNSET_LAT, lon=UNSET_LON),
        action=au.Action(kind="power", power=True),
        all_lights=True,
    )
    morning = au.Rule(
        name=tr("automation.example_morning_name"),
        trigger=au.Trigger(kind="time", time="07:00"),
        action=au.Action(kind="white", bright=70, temp=40, fade_min=15),
        all_lights=True,
    )
    return {"sunset": sunset, "morning": morning}


class RuleRow(QFrame):
    """Listedeki tek kural: ad, özet, hedefler, durum, aç/kapa anahtarı ve düğmeler."""

    def __init__(self, rule: au.Rule, summary: str, targets: str, status: str, last: str, running: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rule_id = rule.id
        self.setObjectName("card")
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 12)
        box.setSpacing(4)
        head = QHBoxLayout()
        self.name_label = QLabel(rule.name)
        self.name_label.setObjectName("value")
        self.name_label.setWordWrap(True)
        self.switch = ToggleSwitch()
        self.switch.set_on(rule.enabled)
        head.addWidget(self.name_label, 1)
        head.addWidget(self.switch)
        box.addLayout(head)
        self.summary_label = self._line(summary, "sub")
        self.targets_label = self._line(targets, "note")
        self.status_label = self._line(tr("automation.running") if running else status, "note")
        self.last_label = self._line(last, "note")
        self.last_label.setVisible(bool(last) and not running)
        for label in (self.summary_label, self.targets_label, self.status_label, self.last_label):
            box.addWidget(label)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.run_button = QPushButton(tr("automation.run_now"))
        self.edit_button = QPushButton(tr("automation.edit"))
        self.delete_button = QPushButton(tr("automation.delete"))
        for button, name in ((self.run_button, "ghost"), (self.edit_button, "ghost"), (self.delete_button, "dangerGhost")):
            button.setObjectName(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        buttons.addWidget(self.run_button)
        buttons.addWidget(self.edit_button)
        buttons.addStretch()
        buttons.addWidget(self.delete_button)
        box.addSpacing(4)
        box.addLayout(buttons)

    @staticmethod
    def _line(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label


class AutomationPage(QWidget):
    def __init__(
        self,
        host: AutomationHost,
        lights: Callable[[], list[tuple[str, str]]],
        presets: PresetStore,
        settings: QSettings | None = None,
        confirm: Callable[[QWidget, str], bool] | None = None,
        now: Callable[[], float] = time.time,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.host, self._lights, self._presets, self._settings = host, lights, presets, settings
        self._confirm = confirm or self._default_confirm
        self._now = now
        self.rows: dict[str, RuleRow] = {}
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)

        top = QHBoxLayout()
        self.add_button = QPushButton(tr("automation.add"))
        self.add_button.setObjectName("ghost")
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(lambda: self.add_rule())
        self.pause_button = QPushButton(tr("automation.pause"))
        self.pause_button.setObjectName("ghost")
        self.pause_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pause_button.clicked.connect(lambda: self.host.set_paused(not self.host.scheduler.paused))
        top.addWidget(self.add_button)
        top.addStretch()
        top.addWidget(self.pause_button)
        box.addLayout(top)

        self.paused_banner = QLabel(tr("automation.paused_banner"))
        self.paused_banner.setObjectName("banner")
        self.paused_banner.setWordWrap(True)
        box.addWidget(self.paused_banner)

        self.empty = self._build_empty()
        box.addWidget(self.empty)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(10)
        box.addLayout(self.list_box)
        box.addWidget(self._build_footer())
        box.addStretch()

        host.changed.connect(self.refresh)
        self.refresh()

    # -- yapı -------------------------------------------------------------------------------------

    def _build_empty(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 20, 20, 18)
        box.setSpacing(10)
        title = QLabel(tr("automation.empty_title"))
        title.setObjectName("title")
        body = QLabel(tr("automation.empty_body"))
        body.setObjectName("sub")
        body.setWordWrap(True)
        box.addWidget(title)
        box.addWidget(body)
        self.empty_add_button = QPushButton(tr("automation.empty_add"))
        self.empty_add_button.setObjectName("primary")
        self.empty_add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_add_button.clicked.connect(lambda: self.add_rule())
        box.addWidget(self.empty_add_button)
        self.example_buttons: dict[str, QPushButton] = {}
        row = QHBoxLayout()
        row.setSpacing(8)
        for key in ("sunset", "morning"):
            button = QPushButton(tr(f"automation.example_{key}"))
            button.setObjectName("chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.add_rule(template=example_rules()[k]))
            row.addWidget(button, 1)
            self.example_buttons[key] = button
        box.addLayout(row)
        return card

    def _build_footer(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(8)
        title = QLabel(i18n.upper(tr("automation.limits_title")))
        title.setObjectName("cardTitle")
        self.limits_label = QLabel(tr("automation.limits_body"))
        self.limits_label.setObjectName("note")
        self.limits_label.setWordWrap(True)
        self.limits_label.setTextFormat(Qt.TextFormat.RichText)
        tolerance = QHBoxLayout()
        label = QLabel(tr("automation.tolerance_label"))
        label.setObjectName("muted")
        self.tolerance_spin = QSpinBox()
        self.tolerance_spin.setRange(1, au.MAX_TOLERANCE_MIN)
        self.tolerance_spin.setSuffix(tr("automation.minutes_suffix"))
        self.tolerance_spin.setKeyboardTracking(False)
        self.tolerance_spin.setValue(self.host.store.tolerance_min)
        self.tolerance_spin.valueChanged.connect(self._on_tolerance)
        tolerance.addWidget(label)
        tolerance.addStretch()
        tolerance.addWidget(self.tolerance_spin)
        self.unverified_label = QLabel(tr("common.unverified"))
        self.unverified_label.setObjectName("note")
        self.unverified_label.setWordWrap(True)
        for item in (title, self.limits_label):
            box.addWidget(item)
        box.addLayout(tolerance)
        box.addWidget(self.unverified_label)
        return card

    @staticmethod
    def _default_confirm(parent: QWidget, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
        box.button(QMessageBox.StandardButton.Yes).setText(tr("automation.delete"))
        box.button(QMessageBox.StandardButton.No).setText(tr("controller.cancel"))
        return box.exec() == QMessageBox.StandardButton.Yes

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self.window(), APP_NAME, text)

    # -- liste ----------------------------------------------------------------------------------------

    def _preset_name(self, key: str) -> str | None:
        preset = self._presets.get(key)
        return preset.name if preset is not None else None

    def refresh(self) -> None:
        while self.list_box.count():
            item = self.list_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()  # deleteLater olay döngüsüne dönene kadar bekler; o sırada eski satır çizilmesin
                widget.setParent(None)
                widget.deleteLater()
        self.rows = {}
        host = self.host
        rules = host.store.rules
        names = {light_id: name for light_id, name in self._lights()}
        now = self._now()
        paused = host.scheduler.paused
        for rule in rules:
            if not rule.enabled:
                status = tr("automation.status_disabled")
            elif paused and rule.trigger.kind != "startup":
                status = tr("automation.status_paused")
            elif rule.trigger.kind == "startup":
                status = ""
            else:
                status = next_text(host.scheduler.next_run(rule, now), now, host.scheduler.zone)
            row = RuleRow(
                rule,
                summary_text(rule, self._preset_name),
                targets_text(rule, names),
                status,
                last_text(host.last.get(rule.id)),
                host.is_running(rule.id),
            )
            row.status_label.setVisible(bool(row.status_label.text()))
            row.switch.clicked.connect(lambda on, rid=rule.id: self.set_enabled(rid, on))
            row.run_button.clicked.connect(lambda _=False, rid=rule.id: self.run_now(rid))
            row.edit_button.clicked.connect(lambda _=False, rid=rule.id: self.edit_rule(rid))
            row.delete_button.clicked.connect(lambda _=False, rid=rule.id: self.delete_rule(rid))
            self.list_box.addWidget(row)
            self.rows[rule.id] = row
        self.empty.setVisible(not rules)
        self.add_button.setVisible(bool(rules))
        self.paused_banner.setVisible(paused)
        self.pause_button.setText(tr("automation.resume") if paused else tr("automation.pause"))
        self.tolerance_spin.blockSignals(True)
        self.tolerance_spin.setValue(host.store.tolerance_min)
        self.tolerance_spin.blockSignals(False)

    # -- işlemler ---------------------------------------------------------------------------------------

    def _dialog(self, rule: au.Rule | None = None, template: au.Rule | None = None) -> au.Rule | None:
        dialog = RuleDialog(self._lights(), self._presets, rule=rule, template=template, settings=self._settings, parent=self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.rule

    def add_rule(self, template: au.Rule | None = None) -> bool:
        rule = self._dialog(template=template)
        if rule is None:
            return False
        return self._save(lambda: self.host.add_rule(rule))

    def edit_rule(self, rule_id: str) -> bool:
        current = self.host.store.get(rule_id)
        if current is None:
            return False
        rule = self._dialog(rule=current)
        if rule is None:
            return False
        return self._save(lambda: self.host.update_rule(rule))

    def _save(self, action: Callable[[], object]) -> bool:
        try:
            action()
        except au.RuleError as exc:
            self._warn(error_text(exc))
            return False
        except OSError as exc:
            self._warn(tr("automation.error_write", error=exc))
            return False
        return True

    def delete_rule(self, rule_id: str) -> bool:
        rule = self.host.store.get(rule_id)
        if rule is None or not self._confirm(self.window(), tr("automation.delete_confirm", name=rule.name)):
            return False
        return self._save(lambda: self.host.delete_rule(rule_id))

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        return self._save(lambda: self.host.set_enabled(rule_id, enabled))

    def run_now(self, rule_id: str) -> bool:
        rule = self.host.store.get(rule_id)
        if rule is None:
            return False
        self.host.run(rule)
        return True

    def _on_tolerance(self, minutes: int) -> None:
        self._save(lambda: self.host.set_tolerance(minutes))
