"""Ana pencere."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import light_core as lc

from .energy_page import EnergyPage
from .colors import COOL, NEUTRAL, WARM, accent_for, hex_of, hs_rgb, shade
from .icons import app_icon
from .presets import PRESETS, Preset
from .tray import TrayController
from .widgets import ColorWheel, GradientSlider, PowerButton, StatusPill

MODE_TR = {"white": "Beyaz ışık", "colour": "Renkli", "scene": "Sahne", "music": "Müzik"}
PAGE_WHITE, PAGE_COLOUR = 0, 1


def _dot_icon(rgb: tuple[int, int, int], size: int = 16) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(*rgb))
    p.drawEllipse(3, 3, size * 2 - 6, size * 2 - 6)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


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

        self.setWindowTitle(cfg.name)
        self.setWindowIcon(app_icon())
        self._build()
        self._wire()
        self._restore_geometry()
        if use_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self._setup_tray()
        self.set_devices([cfg], cfg.device_id)
        self._apply_state(self._state)
        self._on_status("Bağlanılıyor…")

    # ------------------------------------------------------------------ yapı

    def set_devices(self, devices: list[lc.Config], selected: str) -> None:
        """Başlıktaki ışık seçici menüsünü yeniler."""
        self.device_menu.clear()
        self._device_actions = {}
        for dev in devices:
            action = self.device_menu.addAction(_dot_icon(WARM if dev.device_id == selected else (90, 98, 116)), dev.name)
            action.triggered.connect(lambda _=False, i=dev.device_id: self._choose_device(i))
            self._device_actions[dev.device_id] = action
        if devices:
            self.device_menu.addSeparator()
        self.device_menu.addAction("Işık ekle…", self.addRequested.emit)
        rename = self.device_menu.addAction("Adını değiştir…", self.renameRequested.emit)
        remove = self.device_menu.addAction("Bu ışığı kaldır", self.removeRequested.emit)
        rename.setEnabled(bool(devices))
        remove.setEnabled(bool(devices))
        current = next((d for d in devices if d.device_id == selected), None)
        if current is not None:
            self.cfg = current
        if not devices:
            self.device_button.setText("Işık yok  ▾")
            self.setWindowTitle("Odamdaki Işık")
        else:
            self.device_button.setText(f"{self.cfg.name}  ▾")
            self.setWindowTitle(self.cfg.name)

    def show_empty(self) -> None:
        """Hiç ışık kalmadı."""
        self._state = lc.LightState()
        self._apply_state(self._state)
        self.device_button.setText("Işık yok  ▾")
        self.setWindowTitle("Odamdaki Işık")
        self._set_pill("Işık yok", "idle")
        self.banner.setText("Henüz ışık eklenmedi. Üstteki menüden “Işık ekle…” seçin.")
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
        self._state = lc.LightState()
        self._apply_state(self._state)
        self._on_status("Bağlanılıyor…")

    def _card(self, title: str, value_label: QLabel | None = None) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        box = QVBoxLayout(frame)
        box.setContentsMargins(18, 16, 18, 16)
        box.setSpacing(8)
        row = QHBoxLayout()
        label = QLabel(title.upper())
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
        top_lay.addLayout(head)

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        top_lay.addWidget(self.banner)

        tabs_wrap = QFrame()
        tabs_wrap.setObjectName("segWrap")
        tabs = QHBoxLayout(tabs_wrap)
        tabs.setContentsMargins(4, 4, 4, 4)
        tabs.setSpacing(4)
        self.tab_group = QButtonGroup(self)
        self.tab_control = QPushButton("Kontrol")
        self.tab_energy = QPushButton("Enerji")
        for button in (self.tab_control, self.tab_energy):
            button.setObjectName("seg")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tab_group.addButton(button)
            tabs.addWidget(button)
        self.tab_control.setChecked(True)
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
        self.bright_value = QLabel("%50")
        self.bright_value.setObjectName("value")
        card, box = self._card("Parlaklık", self.bright_value)
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
        self.seg_white = QPushButton("Beyaz")
        self.seg_colour = QPushButton("Renk")
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
        self.temp_value = QLabel("Sıcak")
        self.temp_value.setObjectName("value")
        white_card, white_box = self._card("Işık sıcaklığı", self.temp_value)
        self.temp = GradientSlider([(0.0, WARM), (0.5, NEUTRAL), (1.0, COOL)])
        self.temp.setRange(0, 100)
        white_box.addWidget(self.temp)
        ends = QHBoxLayout()
        warm_label, cool_label = QLabel("Sıcak"), QLabel("Soğuk")
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
        colour_card, colour_box = self._card("Renk", self.hex_label)
        self.wheel = ColorWheel(220)
        colour_box.addWidget(self.wheel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(colour_card)
        self._update_hex()
        self._select_page("white")

        # Hazır ayarlar
        presets_title = QLabel("HAZIR AYARLAR")
        presets_title.setObjectName("cardTitle")
        lay.addWidget(presets_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.preset_buttons: list[QPushButton] = []
        for index, preset in enumerate(PRESETS):
            button = QPushButton(preset.name)
            button.setObjectName("chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(_dot_icon(preset.swatch()))
            button.setProperty("preset", preset.name)
            button.clicked.connect(lambda _checked=False, p=preset: self._on_preset(p))
            grid.addWidget(button, index // 3, index % 3)
            self.preset_buttons.append(button)
        lay.addLayout(grid)

        # Araçlar + günlük
        tools = QHBoxLayout()
        self.log_toggle = QPushButton("Günlük")
        self.log_toggle.setObjectName("ghost")
        self.log_toggle.setCheckable(True)
        self.reconnect_button = QPushButton("Yeniden bağlan")
        self.reconnect_button.setObjectName("ghost")
        self.refresh_button = QPushButton("Durumu oku")
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
        self.log_toggle.toggled.connect(self.log_view.setVisible)
        self.reconnect_button.clicked.connect(self.bridge.reconnect)
        self.refresh_button.clicked.connect(self.bridge.refresh)
        self.bridge.state.connect(self._apply_state)
        self.bridge.status.connect(self._on_status)
        self.bridge.error.connect(self._on_error)
        self.bridge.log.connect(self._on_log)
        self.bridge.connectedChanged.connect(self._on_connected)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.quit_app)

    # ------------------------------------------------------------ kullanıcı

    def _on_power(self) -> None:
        self.bridge.set_power(self._state.power is not True)

    def _on_bright(self, value: int) -> None:
        self.bright_value.setText(f"%{value}")
        if not self._syncing:
            self.bridge.set_brightness(value)

    def _on_temp(self, value: int) -> None:
        self.temp_value.setText("Sıcak" if value < 34 else "Nötr" if value < 67 else "Soğuk")
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
            self.state_label.setText("Açık")
            mode = MODE_TR.get(st.mode or "", "")
            self.sub_label.setText(f"{mode} · %{self.bright.value()}" if mode else f"%{self.bright.value()}")
        elif st.power is False:
            self.state_label.setText("Kapalı")
            self.sub_label.setText("Açmak için dokun")
        else:
            self.state_label.setText("—")
            self.sub_label.setText("Işıktan bilgi bekleniyor")
        if self._tray is not None:
            self._tray.set_tooltip({True: "Açık", False: "Kapalı", None: ""}[st.power])

    def _set_pill(self, text: str, tone: str) -> None:
        self.pill.set_status(text, tone)

    def _on_status(self, text: str) -> None:
        tone = "ok" if text == "Bağlı" else "warn" if text.endswith("…") else "bad"
        self._set_pill(text, tone)

    def _on_connected(self, ok: bool) -> None:
        if ok:
            self.banner.hide()

    def _on_error(self, text: str) -> None:
        self.banner.setText(text)
        self.banner.show()
        self._on_log("HATA: " + text)

    def _on_log(self, text: str) -> None:
        self.log_view.appendPlainText(text)

    # ----------------------------------------------------- tepsi ve kapanış

    def _setup_tray(self) -> None:
        tray = TrayController(app_icon(), self.cfg.name, self)
        tray.power_requested.connect(self.bridge.set_power)
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
                self._tray.notify(self.cfg.name, "Uygulama sistem tepsisinde çalışmaya devam ediyor.")
            return
        if self._tray is not None:
            self._tray.hide()
        event.accept()
