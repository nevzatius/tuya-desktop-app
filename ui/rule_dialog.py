"""Otomasyon kuralı ekleme/düzenleme penceresi. Kaydetmez; doğrulanmış `Rule` verir (kaydetmeyi sekme yapar)."""

from __future__ import annotations

import copy

from PySide6.QtCore import QLocale, QSettings, QTime, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

import automation as au
import i18n
from i18n import tr

from .automation_text import error_text
from .presets import PresetStore
from .scene_editor import SceneEditor

TRIGGERS = ("time", "sun", "startup")
ACTIONS = ("power_on", "power_off", "brightness", "white", "colour", "preset")
UNSET_LAT, UNSET_LON = -91.0, -181.0  # "girilmedi" (özel metinle "—" görünür); doğrulama bunu reddeder
LAST_LAT_KEY, LAST_LON_KEY = "automation/lat", "automation/lon"


def _label(text: str, name: str = "muted") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


class RuleDialog(QDialog):
    def __init__(
        self,
        lights: list[tuple[str, str]],
        presets: PresetStore,
        rule: au.Rule | None = None,
        template: au.Rule | None = None,
        settings: QSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.rule: au.Rule | None = None
        self._editing = rule
        self._lights, self._presets, self._settings = lights, presets, settings
        self.setWindowTitle(tr("automation.dialog_edit") if rule else tr("automation.dialog_new"))
        self.setMinimumSize(430, 560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("content")
        self._box = QVBoxLayout(body)
        self._box.setContentsMargins(22, 18, 22, 12)
        self._box.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_name()
        self._build_trigger()
        self._build_action()
        self._build_fade()
        self._build_lights()
        self._box.addStretch()

        footer = QWidget()
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(22, 8, 22, 16)
        self.error = QLabel()
        self.error.setObjectName("banner")
        self.error.setWordWrap(True)
        self.error.hide()
        foot.addWidget(self.error)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("controller.cancel"))
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton(tr("presets.save"))
        self.save_button.setObjectName("primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        foot.addLayout(buttons)
        outer.addWidget(footer)

        self._load(rule or template)

    # -- yapı -------------------------------------------------------------------------------------

    def _build_name(self) -> None:
        self._box.addWidget(_label(tr("automation.name_label")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("automation.name_placeholder"))
        self._box.addWidget(self.name_edit)

    def _locale(self) -> QLocale:
        return QLocale("tr_TR") if i18n.language() == "tr" else QLocale("en_US")

    def _build_trigger(self) -> None:
        self._box.addSpacing(6)
        self._box.addWidget(_label(tr("automation.trigger_label")))
        self.trigger_combo = QComboBox()
        for kind in TRIGGERS:
            self.trigger_combo.addItem(tr(f"automation.trigger_{kind}"), kind)
        self._box.addWidget(self.trigger_combo)
        self.trigger_stack = QStackedWidget()
        self._box.addWidget(self.trigger_stack)

        time_page = QWidget()
        time_box = QVBoxLayout(time_page)
        time_box.setContentsMargins(0, 0, 0, 0)
        time_box.addWidget(_label(tr("automation.time_label")))
        self.time_edit = QTimeEdit(QTime(7, 0))
        self.time_edit.setDisplayFormat("HH:mm")
        time_box.addWidget(self.time_edit)
        self.trigger_stack.addWidget(time_page)

        sun_page = QWidget()
        sun_box = QVBoxLayout(sun_page)
        sun_box.setContentsMargins(0, 0, 0, 0)
        sun_box.setSpacing(6)
        sun_box.addWidget(_label(tr("automation.sun_event_label")))
        self.event_combo = QComboBox()
        for event in au.SUN_EVENTS:
            self.event_combo.addItem(tr(f"automation.event_{event}"), event)
        self.event_combo.setCurrentIndex(1)
        sun_box.addWidget(self.event_combo)
        sun_box.addWidget(_label(tr("automation.offset_label")))
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-au.MAX_OFFSET_MIN, au.MAX_OFFSET_MIN)
        self.offset_spin.setSuffix(tr("automation.minutes_suffix"))
        sun_box.addWidget(self.offset_spin)
        coords = QHBoxLayout()
        self.lat_spin = self._coord_spin(UNSET_LAT, 90.0)
        self.lon_spin = self._coord_spin(UNSET_LON, 180.0)
        for caption, spin in ((tr("automation.lat_label"), self.lat_spin), (tr("automation.lon_label"), self.lon_spin)):
            column = QVBoxLayout()
            column.setSpacing(2)
            column.addWidget(_label(caption))
            column.addWidget(spin)
            coords.addLayout(column)
        sun_box.addLayout(coords)
        sun_box.addWidget(_label(tr("automation.coords_hint"), "note"))
        self.trigger_stack.addWidget(sun_page)

        startup_page = QWidget()
        startup_box = QVBoxLayout(startup_page)
        startup_box.setContentsMargins(0, 0, 0, 0)
        startup_box.addWidget(_label(tr("automation.startup_hint"), "note"))
        self.trigger_stack.addWidget(startup_page)

        self.days_holder = QWidget()
        days_box = QVBoxLayout(self.days_holder)
        days_box.setContentsMargins(0, 4, 0, 0)
        days_box.setSpacing(4)
        days_box.addWidget(_label(tr("automation.days_label")))
        row = QHBoxLayout()
        row.setSpacing(5)
        self.day_buttons: list[QPushButton] = []
        for day in range(7):
            button = QPushButton(tr(f"day.{day}"))
            button.setObjectName("day")
            button.setCheckable(True)
            button.setChecked(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button, 1)
            self.day_buttons.append(button)
        days_box.addLayout(row)
        self._box.addWidget(self.days_holder)
        self.trigger_combo.currentIndexChanged.connect(self._on_trigger)

    def _coord_spin(self, unset: float, high: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setLocale(self._locale())
        spin.setDecimals(4)
        spin.setRange(unset, high)
        spin.setSpecialValueText("—")  # en küçük değer = girilmedi
        spin.setValue(unset)
        spin.setKeyboardTracking(False)
        return spin

    def _build_action(self) -> None:
        self._box.addSpacing(6)
        self._box.addWidget(_label(tr("automation.action_label")))
        self.action_combo = QComboBox()
        for action in ACTIONS:
            self.action_combo.addItem(tr(f"automation.action_{action}"), action)
        self._box.addWidget(self.action_combo)
        self.action_stack = QStackedWidget()
        self._box.addWidget(self.action_stack)

        self.action_stack.addWidget(QWidget())  # güç: ek değer yok

        scene_page = QWidget()
        scene_box = QVBoxLayout(scene_page)
        scene_box.setContentsMargins(0, 0, 0, 0)
        self.scene = SceneEditor("white", wheel_size=170)
        scene_box.addWidget(self.scene)
        self.brightness_hint = _label(tr("automation.brightness_hint"), "note")
        scene_box.addWidget(self.brightness_hint)
        self.action_stack.addWidget(scene_page)

        preset_page = QWidget()
        preset_box = QVBoxLayout(preset_page)
        preset_box.setContentsMargins(0, 0, 0, 0)
        preset_box.addWidget(_label(tr("automation.preset_label")))
        self.preset_combo = QComboBox()
        for preset in self._presets.all():
            self.preset_combo.addItem(preset.name, preset.key)
        preset_box.addWidget(self.preset_combo)
        self.action_stack.addWidget(preset_page)
        self.action_combo.currentIndexChanged.connect(self._on_action)

    def _build_fade(self) -> None:
        self._box.addSpacing(6)
        row = QHBoxLayout()
        self.fade_check = QCheckBox(tr("automation.fade_check"))
        self.fade_spin = QSpinBox()
        self.fade_spin.setRange(1, au.MAX_FADE_MIN)
        self.fade_spin.setValue(15)
        self.fade_label = QLabel(tr("automation.fade_minutes"))
        self.fade_label.setObjectName("muted")
        row.addWidget(self.fade_check)
        row.addStretch()
        row.addWidget(self.fade_spin)
        row.addWidget(self.fade_label)
        self._box.addLayout(row)
        self.fade_hint = _label(tr("automation.fade_hint"), "note")
        self._box.addWidget(self.fade_hint)
        self.fade_check.toggled.connect(self._sync_fade)

    def _build_lights(self) -> None:
        self._box.addSpacing(6)
        self._box.addWidget(_label(tr("automation.lights_label")))
        self.radio_all = QRadioButton(tr("automation.lights_all"))
        self.radio_some = QRadioButton(tr("automation.lights_selected"))
        group = QButtonGroup(self)
        group.addButton(self.radio_all)
        group.addButton(self.radio_some)
        self._lights_group = group
        self.radio_all.setChecked(True)
        self._box.addWidget(self.radio_all)
        self._box.addWidget(self.radio_some)
        self.lights_list = QListWidget()
        self.lights_list.setFixedHeight(120)
        for light_id, name in self._lights:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, light_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lights_list.addItem(item)
        self._box.addWidget(self.lights_list)
        self.radio_all.toggled.connect(self._sync_lights)

    # -- görünürlük ---------------------------------------------------------------------------------

    def _on_trigger(self) -> None:
        kind = self.trigger_combo.currentData()
        self.trigger_stack.setCurrentIndex(TRIGGERS.index(kind))
        self.days_holder.setVisible(kind != "startup")

    def _on_action(self) -> None:
        action = self.action_combo.currentData()
        if action in ("power_on", "power_off"):
            self.action_stack.setCurrentIndex(0)
        elif action == "preset":
            self.action_stack.setCurrentIndex(2)
        else:
            self.scene.set_kind(action)
            self.brightness_hint.setVisible(action == "brightness")
            self.action_stack.setCurrentIndex(1)
        self._sync_fade()

    def _sync_fade(self) -> None:
        fadeable = self.action_combo.currentData() not in ("power_on", "power_off")
        self.fade_check.setEnabled(fadeable)
        if not fadeable:
            self.fade_check.setChecked(False)
        for widget in (self.fade_spin, self.fade_label):
            widget.setEnabled(fadeable and self.fade_check.isChecked())

    def _sync_lights(self) -> None:
        self.lights_list.setEnabled(self.radio_some.isChecked())

    # -- kuraldan forma / formdan kurala ------------------------------------------------------------------

    def _remembered(self, key: str, unset: float) -> float:
        if self._settings is None:
            return unset
        try:
            return float(self._settings.value(key, unset))
        except (TypeError, ValueError):
            return unset

    def _load(self, rule: au.Rule | None) -> None:
        self.lat_spin.setValue(self._remembered(LAST_LAT_KEY, UNSET_LAT))
        self.lon_spin.setValue(self._remembered(LAST_LON_KEY, UNSET_LON))
        if rule is None:
            self._on_trigger()
            self._on_action()
            self._sync_lights()
            return
        self.name_edit.setText(rule.name)
        trigger, action = rule.trigger, rule.action
        self.trigger_combo.setCurrentIndex(TRIGGERS.index(trigger.kind))
        if trigger.kind == "time":
            hour, minute = au.parse_hhmm(trigger.time)
            self.time_edit.setTime(QTime(hour, minute))
        elif trigger.kind == "sun":
            self.event_combo.setCurrentIndex(au.SUN_EVENTS.index(trigger.event))
            self.offset_spin.setValue(trigger.offset)
            if trigger.lat > UNSET_LAT:  # örneklerde koordinat boştur: hatırlanan (ya da boş) kalır
                self.lat_spin.setValue(trigger.lat)
            if trigger.lon > UNSET_LON:
                self.lon_spin.setValue(trigger.lon)
        for day, button in enumerate(self.day_buttons):
            button.setChecked(day in trigger.days or trigger.kind == "startup")
        key = "power_on" if action.kind == "power" and action.power else "power_off" if action.kind == "power" else action.kind
        self.action_combo.setCurrentIndex(ACTIONS.index(key))
        self.scene.set_values("colour" if action.kind == "colour" else "white", action.bright, action.temp, action.hue, action.sat)
        if action.kind == "preset":
            index = self.preset_combo.findData(action.preset)
            if index < 0:  # silinmiş hazır ayar: kural sessizce değişmesin, çalışınca bildirim gelir
                self.preset_combo.addItem(tr("automation.preset_deleted"), action.preset)
                index = self.preset_combo.count() - 1
            self.preset_combo.setCurrentIndex(index)
        if action.fade_min:
            self.fade_check.setChecked(True)
            self.fade_spin.setValue(action.fade_min)
        known = {light_id for light_id, _ in self._lights}
        if rule.all_lights:
            self.radio_all.setChecked(True)
        else:
            self.radio_some.setChecked(True)
            for index in range(self.lights_list.count()):
                item = self.lights_list.item(index)
                if item.data(Qt.ItemDataRole.UserRole) in rule.lights:
                    item.setCheckState(Qt.CheckState.Checked)
            for light_id in rule.lights:
                if light_id not in known:  # kaldırılmış ışık: görünür kalsın, kullanıcı isterse kaldırır
                    item = QListWidgetItem(tr("automation.target_missing"))
                    item.setData(Qt.ItemDataRole.UserRole, light_id)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                    self.lights_list.addItem(item)
        self._on_trigger()
        self._on_action()
        self._sync_lights()
        self._sync_fade()

    def build_rule(self) -> au.Rule:
        """Formdaki değerlerden doğrulanmış kural; geçersizse `RuleError`."""
        kind = self.trigger_combo.currentData()
        trigger = au.Trigger(kind=kind)
        if kind == "time":
            trigger.time = self.time_edit.time().toString("HH:mm")
        if kind == "sun":
            trigger.event = self.event_combo.currentData()
            trigger.offset = self.offset_spin.value()
            trigger.lat = self.lat_spin.value()
            trigger.lon = self.lon_spin.value()
        if kind != "startup":
            trigger.days = [day for day, button in enumerate(self.day_buttons) if button.isChecked()]
        choice = self.action_combo.currentData()
        values = self.scene.values()
        if choice in ("power_on", "power_off"):
            action = au.Action(kind="power", power=choice == "power_on")
        elif choice == "brightness":
            action = au.Action(kind="brightness", bright=int(values["bright"]))
        elif choice == "white":
            action = au.Action(kind="white", bright=int(values["bright"]), temp=int(values["temp"]))
        elif choice == "colour":
            action = au.Action(kind="colour", bright=int(values["bright"]), hue=int(values["hue"]), sat=int(values["sat"]))
        else:
            action = au.Action(kind="preset", preset=str(self.preset_combo.currentData() or ""))
        if self.fade_check.isChecked() and choice not in ("power_on", "power_off"):
            action.fade_min = self.fade_spin.value()
        all_lights = self.radio_all.isChecked()
        chosen = [
            str(self.lights_list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self.lights_list.count())
            if self.lights_list.item(i).checkState() == Qt.CheckState.Checked
        ]
        rule = copy.deepcopy(self._editing) if self._editing is not None else au.Rule()
        rule.name = au.clean_name(self.name_edit.text())
        rule.trigger, rule.action = trigger, action
        rule.all_lights, rule.lights = all_lights, ([] if all_lights else chosen)
        rule.validate()
        return rule

    def accept(self) -> None:  # noqa: D102 - Qt geçersiz kılma
        try:
            rule = self.build_rule()
        except au.RuleError as exc:
            self.error.setText(error_text(exc))
            self.error.show()
            return
        if rule.trigger.kind == "sun" and self._settings is not None:  # bir sonraki kural için konumu hatırla
            self._settings.setValue(LAST_LAT_KEY, rule.trigger.lat)
            self._settings.setValue(LAST_LON_KEY, rule.trigger.lon)
        self.rule = rule
        super().accept()
