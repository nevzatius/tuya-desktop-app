"""Ana pencere."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QActionGroup, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import asyncio

import diagnostics as diag
import i18n
import light_core as lc
from i18n import tr
from version import APP_NAME, APP_URL

from .automation_page import AutomationPage
from .energy_page import EnergyPage
from .colors import COOL, NEUTRAL, WARM, accent_for, hex_of, hs_rgb, shade
from .icons import app_icon
from .presets import Preset, PresetStore
from .presets_view import PresetsSection, dot_icon
from .tray import TrayController
from .trouble import BLUETOOTH_SETTINGS_URL, TroubleshootCard
from .widgets import ColorWheel, GradientSlider, PowerButton, StatusPill
from .workers import Worker

PAGE_WHITE, PAGE_COLOUR = 0, 1
ISSUES_URL = f"{APP_URL}/issues/new/choose"


def default_bluetooth_check() -> str:
    """Bluetooth'u kısa bir taramayla dener (arka plan iş parçacığında çağrılır)."""
    return asyncio.run(lc.check_bluetooth())


def default_open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


class MainWindow(QMainWindow):
    deviceChosen = Signal(str)  # menüden başka ışık seçildi (cihaz kimliği)
    addRequested = Signal()
    renameRequested = Signal()
    removeRequested = Signal()

    def __init__(
        self,
        cfg: lc.Config,
        bridge,
        settings: QSettings | None = None,
        use_tray: bool = True,
        energy_log=None,
        preset_store: PresetStore | None = None,
        automation_host=None,
        hotkey_manager=None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.bridge = bridge
        self._settings = settings or QSettings("TuyaLight", "RoomLight")
        self._state = lc.LightState()
        self._syncing = False
        self._quitting = False
        self._tray: TrayController | None = None
        self._tray_hint_shown = False
        self._energy_log = energy_log
        self._automation_host = automation_host
        self._hotkey_manager = hotkey_manager
        self.preset_store = preset_store if preset_store is not None else PresetStore()  # varsayılan: diske yazmayan, yalnızca yerleşik ayarlar
        self.events = diag.RecentEvents()  # tanılama raporu için son hatalar ve günlük satırları
        self._devices_list: list[lc.Config] = [cfg]
        self._connected: bool | None = None
        self._bt_state = ""
        self._bt_worker: Worker | None = None
        self.bluetooth_check = default_bluetooth_check  # testlerde değiştirilebilir
        self.open_url = default_open_url

        self.setWindowTitle(cfg.name)
        self.setWindowIcon(app_icon())
        self._build()
        self._wire()
        self._restore_geometry()
        if use_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()
        self.set_devices([cfg], cfg.device_id)
        self._apply_state(self._state)
        self._on_status(tr("status.connecting"))

    @property
    def has_tray(self) -> bool:
        return self._tray is not None

    @property
    def preset_buttons(self) -> list[QPushButton]:
        return self.presets_section.buttons

    def apply_preset_key(self, key: str) -> bool:
        """Hazır ayarı kimliğiyle uygular (tepsi menüsü, genel kısayol)."""
        preset = self.preset_store.get(key)
        if preset is None:
            return False
        self._on_preset(preset)
        return True

    def current_scene(self) -> dict:
        """Ekranda görünen ayar (hazır ayar olarak kaydetmek için)."""
        hue, sat = self.wheel.hs()
        mode = "colour" if self.stack.currentIndex() == PAGE_COLOUR else "white"
        return {"mode": mode, "bright": self.bright.value(), "temp": self.temp.value(), "hue": hue, "sat": sat}

    # ------------------------------------------------------------------ yapı

    def _build_settings_menu(self) -> None:
        """Ayarlar menüsü: şimdilik dil seçimi (Sistem dili / Türkçe / English)."""
        language_menu = self.settings_menu.addMenu(tr("main.language"))
        group = QActionGroup(language_menu)
        group.setExclusive(True)
        current = str(self._settings.value(i18n.SETTINGS_KEY, i18n.AUTO))
        self.language_actions: dict[str, object] = {}
        choices = [(i18n.AUTO, tr("main.language_auto")), *i18n.LANGUAGES.items()]
        for code, label in choices:
            action = language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == current or (current not in dict(choices) and code == i18n.AUTO))
            action.triggered.connect(lambda _=False, c=code: self._on_language(c))
            group.addAction(action)
            self.language_actions[code] = action
        self.settings_menu.addSeparator()
        self.copy_report_action = self.settings_menu.addAction(tr("main.copy_report"), lambda: self.copy_report())
        self.report_problem_action = self.settings_menu.addAction(tr("main.report_problem"), lambda: self.open_url(ISSUES_URL))

    def _on_language(self, code: str) -> None:
        """Seçimi kaydeder; arayüz çalışırken yeniden çevrilmez, yeni dil bir sonraki açılışta geçerli olur."""
        if str(self._settings.value(i18n.SETTINGS_KEY, i18n.AUTO)) == code:
            return
        self._settings.setValue(i18n.SETTINGS_KEY, code)
        self.show_info(tr("main.language_restart"))

    def show_info(self, text: str) -> None:
        QMessageBox.information(self, APP_NAME, text)

    def notice(self, text: str) -> None:
        """Pencere kapalı olsa da görünen kısa bildirim: tepsi balonu, tepsi yoksa hata bandı."""
        self.events.add_log(text)
        if self._tray is not None:
            self._tray.notify(APP_NAME, text)
        else:
            self.banner.setText(text)
            self.banner.show()

    def set_devices(self, devices: list[lc.Config], selected: str) -> None:
        """Başlıktaki ışık seçici menüsünü yeniler."""
        self._devices_list = list(devices)
        self.device_menu.clear()
        self._device_actions = {}
        for dev in devices:
            action = self.device_menu.addAction(dot_icon(WARM if dev.device_id == selected else (90, 98, 116)), dev.name)
            action.triggered.connect(lambda _=False, i=dev.device_id: self._choose_device(i))
            self._device_actions[dev.device_id] = action
        if devices:
            self.device_menu.addSeparator()
        self.device_menu.addAction(tr("main.add_light"), self.addRequested.emit)
        rename = self.device_menu.addAction(tr("main.rename"), self.renameRequested.emit)
        remove = self.device_menu.addAction(tr("main.remove"), self.removeRequested.emit)
        rename.setEnabled(bool(devices))
        remove.setEnabled(bool(devices))
        current = next((d for d in devices if d.device_id == selected), None)
        if current is not None:
            self.cfg = current
        if not devices:
            self.device_button.setText(tr("main.no_light_button"))
            self.setWindowTitle(APP_NAME)
        else:
            self.device_button.setText(f"{self.cfg.name}  ▾")
            self.setWindowTitle(self.cfg.name)
        page = getattr(self, "automation_page", None)
        if page is not None:  # ışık adları kural özetlerinde görünür
            page.refresh()

    def show_empty(self) -> None:
        """Hiç ışık kalmadı."""
        self._state = lc.LightState()
        self._apply_state(self._state)
        self.device_button.setText(tr("main.no_light_button"))
        self.setWindowTitle(APP_NAME)
        self._set_pill(tr("status.no_light"), "idle")
        self.banner.setText(tr("main.no_light_banner"))
        self.banner.show()

    def _choose_device(self, device_id: str) -> None:
        if device_id != self.cfg.device_id:
            self.deviceChosen.emit(device_id)

    def set_device(self, cfg: lc.Config) -> None:
        """Başka ışığa geçildi: ekranı sıfırla (yeni durum bağlanınca gelir)."""
        self.cfg = cfg
        self.device_button.setText(f"{cfg.name}  ▾")
        self.setWindowTitle(cfg.name)
        if self._tray is not None:
            self._tray.set_title(cfg.name)
        self.banner.hide()
        self.trouble.hide()
        self._state = lc.LightState()
        self._apply_state(self._state)
        self._on_status(tr("status.connecting"))

    def _card(self, title: str, value_label: QLabel | None = None) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        box = QVBoxLayout(frame)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(8)
        row = QHBoxLayout()
        label = QLabel(i18n.upper(title))
        label.setObjectName("cardTitle")
        row.addWidget(label)
        row.addStretch()
        if value_label is not None:
            row.addWidget(value_label)
        box.addLayout(row)
        return frame, box

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Üst alan (kaydırılmaz): ışık seçici, bağlantı durumu, hata bandı, sekmeler
        top = QWidget()
        top.setObjectName("content")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(24, 22, 24, 10)
        top_lay.setSpacing(12)
        head = QHBoxLayout()
        self.device_button = QPushButton()
        self.device_button.setObjectName("deviceBtn")
        self.device_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.device_menu = QMenu(self.device_button)
        self.device_button.setMenu(self.device_menu)
        self.pill = StatusPill()
        head.addWidget(self.device_button)
        head.addStretch()
        head.addWidget(self.pill)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("iconBtn")
        self.settings_button.setToolTip(tr("main.settings"))
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_menu = QMenu(self.settings_button)
        self.settings_button.setMenu(self.settings_menu)
        self._build_settings_menu()
        head.addWidget(self.settings_button)
        top_lay.addLayout(head)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        top_lay.addWidget(self.banner)
        self.trouble = TroubleshootCard()  # "ışık bulunamadı" için sorun giderici
        self.trouble.hide()
        self.trouble.retryRequested.connect(self._retry)
        self.trouble.recheckRequested.connect(self._check_bluetooth)
        self.trouble.copyReportRequested.connect(self.copy_report)
        self.trouble.openBluetoothSettings.connect(lambda: self.open_url(BLUETOOTH_SETTINGS_URL))
        top_lay.addWidget(self.trouble)

        tabs_wrap = QFrame()
        tabs_wrap.setObjectName("segWrap")
        tabs = QHBoxLayout(tabs_wrap)
        tabs.setContentsMargins(4, 4, 4, 4)
        tabs.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        self.tab_control = QPushButton(tr("main.tab_control"))
        self.tab_energy = QPushButton(tr("main.tab_energy"))
        self.tab_automation = QPushButton(tr("main.tab_automation"))
        for button in (self.tab_control, self.tab_energy, self.tab_automation):
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button)
            tabs.addWidget(button)
        self.tab_control.setChecked(True)
        self.tab_automation.setVisible(self._automation_host is not None)
        top_lay.addWidget(tabs_wrap)
        outer.addWidget(top)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pages.addWidget(scroll)
        content = QWidget()
        content.setObjectName("content")
        scroll.setWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 12, 24, 24)
        lay.setSpacing(16)

        self.energy = EnergyPage(self._settings, self._energy_log)
        energy_scroll = QScrollArea()
        energy_scroll.setWidgetResizable(True)
        energy_scroll.setFrameShape(QFrame.Shape.NoFrame)
        energy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        energy_holder = QWidget()
        energy_holder.setObjectName("content")
        holder_lay = QVBoxLayout(energy_holder)
        holder_lay.setContentsMargins(24, 12, 24, 24)
        holder_lay.addWidget(self.energy)
        energy_scroll.setWidget(energy_holder)
        self.pages.addWidget(energy_scroll)

        self.automation_page: AutomationPage | None = None
        automation_scroll = QScrollArea()
        automation_scroll.setWidgetResizable(True)
        automation_scroll.setFrameShape(QFrame.Shape.NoFrame)
        automation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        automation_holder = QWidget()
        automation_holder.setObjectName("content")
        automation_lay = QVBoxLayout(automation_holder)
        automation_lay.setContentsMargins(24, 12, 24, 24)
        if self._automation_host is not None:
            self.automation_page = AutomationPage(
                self._automation_host,
                lambda: [(d.device_id, d.name) for d in self._devices_list],
                self.preset_store,
                self._settings,
            )
            automation_lay.addWidget(self.automation_page)
        automation_scroll.setWidget(automation_holder)
        self.pages.addWidget(automation_scroll)

        # Güç düğmesi
        self.power = PowerButton()
        lay.addWidget(self.power, 0, Qt.AlignmentFlag.AlignHCenter)
        self.state_label = QLabel("—")
        self.state_label.setObjectName("stateBig")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("sub")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.state_label)
        lay.addWidget(self.sub_label)
        lay.addSpacing(4)

        # Parlaklık
        self.bright_value = QLabel(tr("fmt.percent", value=50))
        self.bright_value.setObjectName("value")
        card, box = self._card(tr("main.brightness"), self.bright_value)
        self.bright = GradientSlider(fill=True)
        self.bright.setRange(1, 100)
        self.bright.setValue(50)
        box.addWidget(self.bright)
        lay.addWidget(card)

        # Mod seçici
        seg_wrap = QFrame()
        seg_wrap.setObjectName("segWrap")
        seg_row = QHBoxLayout(seg_wrap)
        seg_row.setContentsMargins(4, 4, 4, 4)
        seg_row.setSpacing(4)
        self.seg_white = QPushButton(tr("main.white"))
        self.seg_colour = QPushButton(tr("main.colour"))
        group = QButtonGroup(self)
        group.setExclusive(True)
        for button in (self.seg_white, self.seg_colour):
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(button)
            seg_row.addWidget(button, 1)
        self.seg_white.setChecked(True)
        self._seg_group = group
        lay.addWidget(seg_wrap)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        # Sayfa 0: beyaz sıcaklığı
        self.temp_value = QLabel(tr("main.warm"))
        self.temp_value.setObjectName("value")
        white_card, white_box = self._card(tr("main.temperature"), self.temp_value)
        self.temp = GradientSlider([(0.0, WARM), (0.5, NEUTRAL), (1.0, COOL)])
        self.temp.setRange(0, 100)
        white_box.addWidget(self.temp)
        ends = QHBoxLayout()
        warm_label, cool_label = QLabel(tr("main.warm")), QLabel(tr("main.cool"))
        warm_label.setObjectName("muted")
        cool_label.setObjectName("muted")
        ends.addWidget(warm_label)
        ends.addStretch()
        ends.addWidget(cool_label)
        white_box.addLayout(ends)
        self.stack.addWidget(white_card)

        # Sayfa 1: renk çarkı
        self.hex_label = QLabel("")
        self.hex_label.setObjectName("hex")
        colour_card, colour_box = self._card(tr("main.colour"), self.hex_label)
        self.wheel = ColorWheel(220)
        colour_box.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(colour_card)
        self._update_hex()
        self._select_page("white")

        # Hazır ayarlar (yerleşik + kullanıcının kendi ayarları)
        self.presets_section = PresetsSection(self.preset_store, self.current_scene, hotkeys=self._hotkey_manager)
        self.presets_section.applyRequested.connect(self._on_preset)
        lay.addWidget(self.presets_section)

        # Araçlar + günlük
        tools = QHBoxLayout()
        self.log_toggle = QPushButton(tr("main.log"))
        self.log_toggle.setObjectName("ghost")
        self.log_toggle.setCheckable(True)
        self.reconnect_button = QPushButton(tr("main.reconnect"))
        self.reconnect_button.setObjectName("ghost")
        self.refresh_button = QPushButton(tr("main.read_state"))
        self.refresh_button.setObjectName("ghost")
        for button in (self.log_toggle, self.reconnect_button, self.refresh_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        tools.addWidget(self.log_toggle)
        tools.addStretch()
        tools.addWidget(self.refresh_button)
        tools.addWidget(self.reconnect_button)
        lay.addLayout(tools)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        lay.addWidget(self.log_view)
        lay.addStretch()

    def _wire(self) -> None:
        self.power.clicked.connect(self._on_power)
        self.bright.valueChanged.connect(self._on_bright)
        self.temp.valueChanged.connect(self._on_temp)
        self.wheel.changed.connect(self._on_wheel)
        self.seg_white.clicked.connect(lambda: self._on_mode("white"))
        self.seg_colour.clicked.connect(lambda: self._on_mode("colour"))
        self.tab_control.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.tab_energy.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        self.tab_automation.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        if self.automation_page is not None:
            self.presets_section.changed.connect(self.automation_page.refresh)  # özetlerdeki hazır ayar adları
        self.log_toggle.toggled.connect(self.log_view.setVisible)
        self.reconnect_button.clicked.connect(self.bridge.reconnect)
        self.refresh_button.clicked.connect(self.bridge.refresh)
        self.bridge.state.connect(self._apply_state)
        self.bridge.status.connect(self._on_status)
        self.bridge.error.connect(self._on_error)
        problem = getattr(self.bridge, "problem", None)
        if problem is not None:
            problem.connect(self._on_problem)
        self.bridge.log.connect(self._on_log)
        self.bridge.connectedChanged.connect(self._on_connected)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)

    # ------------------------------------------------------------ kullanıcı

    def _on_power(self) -> None:
        self.bridge.set_power(self._state.power is not True)

    def _on_bright(self, value: int) -> None:
        self.bright_value.setText(tr("fmt.percent", value=value))
        if not self._syncing:
            self.bridge.set_brightness(value)

    def _on_temp(self, value: int) -> None:
        self.temp_value.setText(tr("main.warm") if value < 34 else tr("main.neutral") if value < 67 else tr("main.cool"))
        if not self._syncing:
            self.bridge.set_white(self.bright.value(), value)

    def _on_wheel(self, hue: int, sat: int) -> None:
        self._update_hex()
        if not self._syncing:
            self.bridge.set_colour(hue, sat, self.bright.value())

    def _on_mode(self, mode: str) -> None:
        self._select_page(mode)
        if mode == "white":
            self.bridge.set_white(self.bright.value(), self.temp.value())
        else:
            hue, sat = self.wheel.hs()
            self.bridge.set_colour(hue, sat, self.bright.value())

    def _on_preset(self, preset: Preset) -> None:
        self._syncing = True
        try:
            self._select_page(preset.mode)
            self.bright.setValue(preset.bright)
            if preset.mode == "white":
                self.temp.setValue(preset.temp)
            else:
                self.wheel.set_hs(preset.hue, preset.sat)
                self._update_hex()
        finally:
            self._syncing = False
        self.bridge.apply_scene(preset)

    # ---------------------------------------------------------------- durum

    def _select_page(self, mode: str) -> None:
        colour = mode == "colour"
        index = PAGE_COLOUR if colour else PAGE_WHITE
        self.stack.setCurrentIndex(index)
        # Yığın, sadece görünen sayfanın yüksekliği kadar yer kaplasın.
        for page_index in range(self.stack.count()):
            page = self.stack.widget(page_index)
            policy = QSizePolicy.Policy.Preferred if page_index == index else QSizePolicy.Policy.Ignored
            page.setSizePolicy(policy, policy)
        self.stack.updateGeometry()
        (self.seg_colour if colour else self.seg_white).setChecked(True)

    def _update_hex(self) -> None:
        hue, sat = self.wheel.hs()
        self.hex_label.setText(hex_of(hs_rgb(hue, sat)))

    def _apply_state(self, st: lc.LightState) -> None:
        self._state = st
        self._syncing = True
        try:
            pct = lc.bright_to_pct(st.val) if st.mode == "colour" and st.val is not None else st.brightness_pct
            if pct is not None:
                self.bright.setValue(pct)
            if st.temp_pct is not None:
                self.temp.setValue(st.temp_pct)
            if st.hue is not None and st.sat is not None:
                self.wheel.set_hs(st.hue, st.sat)
                self._update_hex()
            if st.mode in ("white", "colour"):
                self._select_page(st.mode)
        finally:
            self._syncing = False

        accent = accent_for(st.power, st.mode, st.temp_pct, st.hue, st.sat)
        self.power.set_state(st.power is True, accent)
        self.bright.set_stops([(0.0, shade(accent, 0.30)), (1.0, accent)])

        if st.power is True:
            self.state_label.setText(tr("state.on"))
            mode = tr(f"mode.{st.mode}") if st.mode in lc.MODES else ""
            percent = tr("fmt.percent", value=self.bright.value())
            self.sub_label.setText(f"{mode} · {percent}" if mode else percent)
        elif st.power is False:
            self.state_label.setText(tr("state.off"))
            self.sub_label.setText(tr("state.tap_to_turn_on"))
        else:
            self.state_label.setText("—")
            self.sub_label.setText(tr("state.waiting"))
        if self._tray is not None:
            self._tray.set_tooltip({True: tr("state.on"), False: tr("state.off"), None: ""}[st.power])

    def _set_pill(self, text: str, tone: str) -> None:
        self.pill.set_status(text, tone)

    def _on_status(self, text: str) -> None:
        tone = "ok" if text == tr("status.connected") else "warn" if text.endswith("…") else "bad"
        self._set_pill(text, tone)

    def _on_connected(self, ok: bool) -> None:
        self._connected = ok
        if ok:
            self.banner.hide()
            self.trouble.hide()

    def _on_error(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.show()
        self.events.add_error(text)
        self._on_log("ERROR: " + text)

    def _on_log(self, text: str) -> None:
        self.events.add_log(text)
        self.log_view.appendPlainText(text)

    # --------------------------------------------------- sorun giderici ve rapor

    def _on_problem(self, kind: str) -> None:
        """Hata türüne göre çözüm: "ışık bulunamadı" için kart, diğerleri için yalnızca bant."""
        self.events.add_error(f"kind={kind}")
        if kind != "not_found":
            self.trouble.hide()
            return
        self.banner.hide()  # kart aynı bilgiyi (ve daha fazlasını) veriyor
        if self.trouble.isHidden():
            self.trouble.show()
            self._check_bluetooth()

    def _check_bluetooth(self) -> None:
        if self._bt_worker is not None:
            return
        self.trouble.set_bluetooth_state("checking")
        worker = Worker(self.bluetooth_check, (), lambda exc: ("unknown", "other"))
        worker.done.connect(self._bluetooth_checked)
        worker.failed.connect(lambda *_: self._bluetooth_checked("unknown"))
        worker.finished.connect(self._bluetooth_worker_finished)
        self._bt_worker = worker
        worker.start()

    def _bluetooth_worker_finished(self) -> None:
        self._bt_worker = None

    def _bluetooth_checked(self, state: object) -> None:
        self._bt_state = str(state)
        self.trouble.set_bluetooth_state(self._bt_state)

    def _retry(self) -> None:
        self.bridge.reconnect()
        self._check_bluetooth()

    def build_report(self) -> str:
        return diag.build_report(
            self._devices_list,
            self.events,
            language=i18n.language(),
            language_setting=str(self._settings.value(i18n.SETTINGS_KEY, i18n.AUTO)),
            connected=self._connected,
            bluetooth=self._bt_state,
        )

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.build_report())
        self.show_info(tr("main.report_copied"))

    # ----------------------------------------------------- tepsi ve kapanış

    def _setup_tray(self) -> None:
        host = self._automation_host
        tray = TrayController(app_icon(), self.cfg.name, self, with_automation=host is not None)
        tray.power_requested.connect(self.bridge.set_power)
        tray.preset_requested.connect(self.apply_preset_key)
        tray.set_presets(self.preset_store.visible())
        self.presets_section.changed.connect(lambda: tray.set_presets(self.preset_store.visible()))
        if host is not None:
            tray.automation_pause_requested.connect(host.set_paused)
            tray.set_automation_paused(host.scheduler.paused)
            host.changed.connect(lambda: tray.set_automation_paused(host.scheduler.paused))
        tray.show_requested.connect(self._toggle_visible)
        tray.quit_requested.connect(self.quit_app)
        tray.show()
        self._tray = tray

    def _toggle_visible(self) -> None:
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _restore_geometry(self) -> None:
        geometry = self._settings.value("geometry")
        if geometry is not None and self.restoreGeometry(geometry):
            return
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry().height() if screen else 900
        self.resize(430, min(860, available - 80))
        self.setMinimumWidth(390)

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._settings.setValue("geometry", self.saveGeometry())
        if self._tray is not None and not self._quitting:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self._tray.notify(self.cfg.name, tr("tray.hint"))
            return
        if self._tray is not None:
            self._tray.hide()
        event.accept()
