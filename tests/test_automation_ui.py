"""Otomasyon sekmesi (Qt, offscreen): ekleme, düzenleme, silme, aç/kapa, "Şimdi çalıştır" ve metinler."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from tuya_ble_sdk import DataPointType  # noqa: E402

import automation as au  # noqa: E402
import devices as dv  # noqa: E402
import i18n  # noqa: E402
import light_core as lc  # noqa: E402
from automation_helpers import FakeBackend, FakeClient, FixedZone, make_rule  # noqa: E402
from ui import automation_text as txt  # noqa: E402
from ui.automation_host import AutomationHost, LightBackend  # noqa: E402
from ui.bridge import LightBridge  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.presets import PresetStore  # noqa: E402
from ui.rule_dialog import RuleDialog  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

A = lc.Config(device_id="light-a-0123456789", local_key="KeyA#0123456789!", uuid="uuid-a", name="Salon")
B = lc.Config(device_id="light-b-0123456789", local_key="KeyB#0123456789!", uuid="uuid-b", name="Yatak odası")


class FakeBridge:
    """MainWindow'un beklediği yüzey (hiçbir şey göndermez)."""

    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class Signals(QObject):
            state = Signal(object)
            status = Signal(str)
            error = Signal(str)
            problem = Signal(str)
            log = Signal(str)
            connectedChanged = Signal(bool)

        self._s = Signals()
        for name in ("state", "status", "error", "problem", "log", "connectedChanged"):
            setattr(self, name, getattr(self._s, name))

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


@pytest.fixture()
def ui(qapp, tmp_path):
    """Pencere + ana makine; arka uç sahte (komutları kaydeder)."""
    backend = FakeBackend(names={A.device_id: "Salon", B.device_id: "Yatak odası"})
    store = au.RuleStore(tmp_path / "automations.json")
    host = AutomationHost(
        store,
        au.EngineState(tmp_path / "state.json"),
        backend,
        resolve_preset=PresetStore().get,
        submit=lambda coro: asyncio.run(coro),
        sleep=lambda s: asyncio.sleep(0),
        retry_delays=(),
    )
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    win = MainWindow(A, FakeBridge(), settings=settings, use_tray=False, preset_store=PresetStore(), automation_host=host)
    win.set_devices([A, B], A.device_id)
    win.resize(430, 1000)
    yield win, win.automation_page, host, backend, settings
    win.close()


def fill(monkeypatch, name="Yeni kural", trigger="time", time=(7, 30), action="power_on", lights="all", **extra):
    """RuleDialog.exec() kullanıcı gibi davranır: formu doldurur ve Kaydet'e basar. Dialog'ları `seen` listesine koyar."""
    seen: list[RuleDialog] = []

    def fake_exec(self):
        seen.append(self)
        self.name_edit.setText(name)
        self.trigger_combo.setCurrentIndex(["time", "sun", "startup"].index(trigger))
        self.time_edit.setTime(self.time_edit.time().__class__(*time))
        if trigger == "sun":
            self.event_combo.setCurrentIndex(extra.get("event", 1))
            self.offset_spin.setValue(extra.get("offset", 0))
            self.lat_spin.setValue(extra.get("lat", 41.0082))
            self.lon_spin.setValue(extra.get("lon", 28.9784))
        for index, button in enumerate(self.day_buttons):
            button.setChecked(index in extra.get("days", range(7)))
        self.action_combo.setCurrentIndex(["power_on", "power_off", "brightness", "white", "colour", "preset"].index(action))
        if "scene" in extra:
            self.scene.set_values(**extra["scene"])
        if "preset" in extra:
            self.preset_combo.setCurrentIndex(self.preset_combo.findData(extra["preset"]))
        if "fade" in extra:
            self.fade_check.setChecked(True)
            self.fade_spin.setValue(extra["fade"])
        if lights == "all":
            self.radio_all.setChecked(True)
        else:
            self.radio_some.setChecked(True)
            for i in range(self.lights_list.count()):
                item = self.lights_list.item(i)
                item.setCheckState(item.checkState().__class__.Checked if item.data(0x0100) in lights else item.checkState().__class__.Unchecked)
        self.save_button.click()
        return QDialog.DialogCode.Accepted if self.rule is not None else QDialog.DialogCode.Rejected

    monkeypatch.setattr(RuleDialog, "exec", fake_exec)
    return seen


# =============================== sekme ve boş durum ===============================


def test_tab_exists_only_with_a_host_and_switches_the_page(ui, qapp, tmp_path):
    win, page, host, backend, _ = ui
    win.show()
    assert win.tab_automation.text() == "Otomasyon" and not win.tab_automation.isHidden()
    win.tab_automation.click()
    assert win.pages.currentIndex() == 2
    win.tab_control.click()
    assert win.pages.currentIndex() == 0
    plain = MainWindow(A, FakeBridge(), settings=QSettings(str(tmp_path / "b.ini"), QSettings.Format.IniFormat), use_tray=False)
    assert plain.tab_automation.isHidden() and plain.automation_page is None
    plain.close()


def test_empty_state_guides_and_is_replaced_by_the_list(ui, monkeypatch):
    win, page, host, backend, _ = ui
    win.show()
    assert not page.empty.isHidden() and page.add_button.isHidden() and page.rows == {}
    assert page.empty_add_button.text() == "İlk otomasyonu ekle"
    assert set(page.example_buttons) == {"sunset", "morning"}
    fill(monkeypatch)
    page.empty_add_button.click()
    assert page.empty.isHidden() and not page.add_button.isHidden() and len(page.rows) == 1


def test_examples_open_a_prefilled_dialog_and_save_nothing_until_confirmed(ui, monkeypatch):
    win, page, host, backend, _ = ui
    seen: list[RuleDialog] = []

    def peek(self):
        seen.append(self)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(RuleDialog, "exec", peek)
    page.example_buttons["sunset"].click()
    dialog = seen[-1]
    assert dialog.name_edit.text() == "Akşam ışığı" and dialog.trigger_combo.currentData() == "sun"
    assert dialog.event_combo.currentData() == "sunset" and dialog.radio_all.isChecked()
    assert dialog.lat_spin.text() == "—" and dialog.lon_spin.text() == "—"  # koordinat uydurulmaz; kullanıcıdan istenir
    page.example_buttons["morning"].click()
    morning = seen[-1]
    assert morning.time_edit.time().toString("HH:mm") == "07:00" and morning.action_combo.currentData() == "white"
    assert morning.fade_check.isChecked() and morning.fade_spin.value() == 15
    assert host.store.rules == []  # vazgeçilince hiçbir şey kaydedilmedi


# =============================== ekleme ===============================


def test_add_time_rule_saves_and_shows_a_readable_summary(ui, monkeypatch):
    win, page, host, backend, _ = ui
    fill(monkeypatch, "Sabah", time=(7, 30), action="white", scene={"mode": "white", "bright": 70, "temp": 20}, days=[0, 1, 2, 3, 4], lights=[A.device_id])
    assert page.add_rule()
    rule = host.store.rules[0]
    assert (rule.name, rule.trigger.time, rule.trigger.days, rule.action.kind) == ("Sabah", "07:30", [0, 1, 2, 3, 4], "white")
    assert (rule.action.bright, rule.action.temp, rule.all_lights, rule.lights) == (70, 20, False, [A.device_id])
    row = page.rows[rule.id]
    assert row.name_label.text() == "Sabah"
    assert row.summary_label.text() == "Hafta içi 07:30 → beyaz ışık, parlaklık %70, Sıcak"
    assert row.targets_label.text() == "Salon" and row.switch.isChecked()
    assert au.RuleStore.load(host.store.path).rules[0].name == "Sabah"  # dosyaya yazıldı


def test_add_sun_rule_with_offset_fade_and_two_lights(ui, monkeypatch):
    win, page, host, backend, settings = ui
    fill(monkeypatch, "Akşam", trigger="sun", event=1, offset=-30, action="brightness", scene={"mode": "white", "bright": 60}, fade=20, lights=[A.device_id, B.device_id])
    assert page.add_rule()
    rule = host.store.rules[0]
    assert (rule.trigger.kind, rule.trigger.event, rule.trigger.offset) == ("sun", "sunset", -30)
    assert rule.trigger.lat == pytest.approx(41.0082) and rule.trigger.lon == pytest.approx(28.9784)
    assert (rule.action.kind, rule.action.bright, rule.action.fade_min) == ("brightness", 60, 20)
    assert page.rows[rule.id].summary_label.text() == "Her gün, gün batımından 30 dk önce → parlaklık %60, 20 dk'da yumuşak geçişle"
    assert page.rows[rule.id].targets_label.text() == "Salon, Yatak odası"
    assert float(settings.value("automation/lat")) == pytest.approx(41.0082)  # sonraki kural için hatırlanır


def test_next_dialog_remembers_the_last_location(ui, monkeypatch):
    win, page, host, backend, settings = ui
    fill(monkeypatch, "Birinci", trigger="sun")
    page.add_rule()
    seen = fill(monkeypatch, "İkinci")
    page.add_rule()
    assert seen[0].lat_spin.value() == pytest.approx(41.0082) and seen[0].lon_spin.value() == pytest.approx(28.9784)


def test_startup_preset_and_colour_rules(ui, monkeypatch):
    win, page, host, backend, _ = ui
    fill(monkeypatch, "Açılış", trigger="startup", action="preset", preset="movie")
    page.add_rule()
    fill(monkeypatch, "Mavi", action="colour", scene={"mode": "colour", "bright": 35, "hue": 240, "sat": 800})
    page.add_rule()
    startup, colour = host.store.rules
    assert (startup.trigger.kind, startup.action.preset) == ("startup", "movie")
    assert (colour.action.hue, colour.action.sat, colour.action.bright) == (240, 800, 35)
    assert page.rows[startup.id].summary_label.text() == "Uygulama açıldığında → “Film” hazır ayarı"
    assert page.rows[startup.id].status_label.isHidden()  # başlangıç kuralında "sonraki" yok


def test_dialog_shows_clear_errors_and_stays_open(ui, qapp):
    win, page, host, backend, _ = ui
    dialog = RuleDialog([(A.device_id, "Salon")], PresetStore(), parent=win)

    def attempt():
        dialog.save_button.click()
        return dialog.error.text() if not dialog.error.isHidden() else None

    assert "ad verin" in attempt() and dialog.rule is None  # ad yok
    dialog.name_edit.setText("Deneme")
    for button in dialog.day_buttons:
        button.setChecked(False)
    assert attempt() == "En az bir gün seçin."
    dialog.day_buttons[0].setChecked(True)
    dialog.radio_some.setChecked(True)
    assert attempt() == "En az bir ışık seçin."
    dialog.radio_all.setChecked(True)
    dialog.trigger_combo.setCurrentIndex(1)  # gün batımı, koordinat girilmedi
    assert "Enlem" in attempt()
    dialog.lat_spin.setValue(41.0)
    dialog.lon_spin.setValue(29.0)
    assert dialog.rule is None
    dialog.save_button.click()
    assert dialog.rule is not None and dialog.rule.trigger.kind == "sun"


def test_fade_is_unavailable_for_power_actions_and_clears_itself(ui):
    win, page, host, backend, _ = ui
    dialog = RuleDialog([(A.device_id, "Salon")], PresetStore(), parent=win)
    dialog.action_combo.setCurrentIndex(3)  # beyaz
    assert dialog.fade_check.isEnabled()
    dialog.fade_check.setChecked(True)
    dialog.action_combo.setCurrentIndex(0)  # ışığı aç
    assert not dialog.fade_check.isEnabled() and not dialog.fade_check.isChecked() and not dialog.fade_spin.isEnabled()
    dialog.name_edit.setText("x")
    assert dialog.build_rule().action.fade_min == 0


def test_light_list_is_disabled_for_all_lights(ui):
    win, page, host, backend, _ = ui
    dialog = RuleDialog([(A.device_id, "Salon"), (B.device_id, "Yatak odası")], PresetStore(), parent=win)
    assert not dialog.lights_list.isEnabled()
    dialog.radio_some.setChecked(True)
    assert dialog.lights_list.isEnabled() and dialog.lights_list.count() == 2


# =============================== düzenleme / silme / aç-kapa ===============================


def add_sample(host, **kwargs):
    rule = make_rule("Örnek", au.Trigger(kind="time", time="07:00", days=[0, 2]), au.Action(kind="brightness", bright=40, fade_min=10), **kwargs)
    return host.add_rule(rule)


def test_edit_opens_the_saved_values_and_saves_changes(ui, monkeypatch):
    win, page, host, backend, _ = ui
    rule = add_sample(host, lights=[A.device_id])
    seen = fill(monkeypatch, "Düzenlenmiş", time=(8, 15), action="brightness", scene={"mode": "white", "bright": 55}, days=[1], fade=5, lights=[B.device_id])
    original_load = RuleDialog._load
    loaded = {}

    def spy(self, r):
        original_load(self, r)
        loaded.update(name=self.name_edit.text(), time=self.time_edit.time().toString("HH:mm"), days=[i for i, b in enumerate(self.day_buttons) if b.isChecked()],
                      action=self.action_combo.currentData(), bright=self.scene.bright.value(), fade=(self.fade_check.isChecked(), self.fade_spin.value()),
                      some=self.radio_some.isChecked())

    monkeypatch.setattr(RuleDialog, "_load", spy)
    assert page.edit_rule(rule.id)
    assert loaded == {"name": "Örnek", "time": "07:00", "days": [0, 2], "action": "brightness", "bright": 40, "fade": (True, 10), "some": True}
    updated = host.store.get(rule.id)
    assert (updated.name, updated.trigger.time, updated.trigger.days, updated.lights) == ("Düzenlenmiş", "08:15", [1], [B.device_id])
    assert (updated.action.bright, updated.action.fade_min) == (55, 5) and updated.id == rule.id and len(host.store.rules) == 1


def test_cancelled_edit_changes_nothing(ui, monkeypatch):
    win, page, host, backend, _ = ui
    rule = add_sample(host)
    monkeypatch.setattr(RuleDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    assert not page.edit_rule(rule.id)
    assert host.store.get(rule.id).name == "Örnek"


def test_delete_asks_first(ui):
    win, page, host, backend, _ = ui
    rule = add_sample(host)
    asked = []
    page._confirm = lambda parent, text: asked.append(text) or False
    assert not page.delete_rule(rule.id) and len(host.store.rules) == 1 and "Örnek" in asked[0]
    page._confirm = lambda parent, text: True
    assert page.delete_rule(rule.id)
    assert host.store.rules == [] and page.rows == {} and page.empty.isVisibleTo(page)
    assert au.RuleStore.load(host.store.path).rules == []


def test_row_buttons_are_wired_to_edit_delete_and_run(ui, monkeypatch):
    win, page, host, backend, _ = ui
    rule = add_sample(host, all_lights=True)
    row = page.rows[rule.id]
    page._confirm = lambda parent, text: True
    row.run_button.click()
    assert backend.commands(A.device_id) and backend.commands(B.device_id)  # tüm ışıklar (ayrıntı: uçtan uca test)
    row.delete_button.click()
    assert host.store.rules == []


def test_switch_enables_and_disables_and_persists(ui):
    win, page, host, backend, _ = ui
    rule = add_sample(host)
    row = page.rows[rule.id]
    assert row.switch.isChecked() and "Sonraki" in row.status_label.text()
    row.switch.click()
    assert not host.store.rules[0].enabled and not page.rows[rule.id].switch.isChecked()
    assert page.rows[rule.id].status_label.text() == "Kapalı"
    assert not au.RuleStore.load(host.store.path).rules[0].enabled
    page.rows[rule.id].switch.click()
    assert host.store.rules[0].enabled and "Sonraki" in page.rows[rule.id].status_label.text()


def test_enabling_a_rule_whose_time_just_passed_does_not_run_it_retroactively(ui):
    win, page, host, backend, _ = ui
    rule = add_sample(host)
    host.set_enabled(rule.id, False)
    host.set_enabled(rule.id, True)  # şu an etkinleştirildi
    host.tick()
    assert backend.calls == []


# =============================== "Şimdi çalıştır" ===============================


def test_run_now_sends_the_command_for_the_rule(ui):
    win, page, host, backend, _ = ui
    rule = host.add_rule(make_rule("Aç", au.Trigger(kind="time", time="03:00"), au.Action(kind="brightness", bright=33), lights=[A.device_id]))
    page.rows[rule.id].run_button.click()
    assert backend.calls == [(A.device_id, au.Command("brightness", bright=33))]
    assert page.rows[rule.id].last_label.text() == "Son çalışma: başarılı" and not page.rows[rule.id].last_label.isHidden()


def test_run_now_works_for_a_disabled_rule_and_reports_failures_in_the_row(ui):
    win, page, host, backend, _ = ui
    backend.fail[A.device_id] = -1
    rule = host.add_rule(make_rule("Kapalı", au.Trigger(kind="time", time="03:00"), au.Action(kind="power", power=True), lights=[A.device_id], enabled=False))
    page.rows[rule.id].run_button.click()
    assert "ulaşılamadı" in page.rows[rule.id].last_label.text() and page.rows[rule.id].last_label.text().startswith("Son çalışma başarısız")


def test_row_shows_running_while_a_fade_is_in_progress(ui):
    win, page, host, backend, _ = ui
    rule = host.add_rule(make_rule("Geçiş", au.Trigger(), au.Action(kind="white", bright=80, temp=50, fade_min=5), lights=[A.device_id]))
    host.running[rule.id] = 1
    host.changed.emit()
    assert page.rows[rule.id].status_label.text() == "Çalışıyor…"
    host.running.clear()
    host.changed.emit()
    assert page.rows[rule.id].status_label.text() != "Çalışıyor…"


def test_run_now_reaches_the_real_bridge_client_for_the_selected_light_and_a_temporary_one_for_the_other(qapp, tmp_path):
    """Uçtan uca: sekme düğmesi -> ana makine -> arka uç -> köprü (sahte istemci). Seçili ışık köprüden, diğeri geçici istemciden."""
    FakeClient.instances = []
    devices = dv.DeviceStore(tmp_path / "devices.json")
    cfg_a, cfg_b = lc.Config(**{**A.__dict__}), lc.Config(**{**B.__dict__})
    devices.add(cfg_a)
    devices.add(cfg_b)
    devices.select(cfg_a.device_id)
    created: dict[str, FakeClient] = {}

    def bridge_factory(cfg, **kwargs):
        created.setdefault(cfg.device_id, FakeClient(cfg, **kwargs))
        return created[cfg.device_id]

    bridge = LightBridge(cfg_a, client_factory=bridge_factory, watch_interval=0.05)
    bridge.start(watchdog=False)
    temporary: list[FakeClient] = []
    backend = LightBackend(devices, bridge, client_factory=lambda cfg: temporary.append(FakeClient(cfg)) or temporary[-1], state_wait=0.2, operation_timeout=5)
    host = AutomationHost(
        au.RuleStore(tmp_path / "automations.json"),
        au.EngineState(),
        backend,
        resolve_preset=PresetStore().get,
        submit=lambda coro: asyncio.run(coro),
        sleep=lambda s: asyncio.sleep(0),
        retry_delays=(),
    )
    win = MainWindow(cfg_a, bridge, settings=QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat), use_tray=False, preset_store=PresetStore(), automation_host=host)
    win.set_devices([cfg_a, cfg_b], cfg_a.device_id)
    try:
        page = win.automation_page
        everywhere = host.add_rule(make_rule("Film modu", au.Trigger(), au.Action(kind="preset", preset="movie"), all_lights=True))
        page.rows[everywhere.id].run_button.click()
        power_off = host.add_rule(make_rule("Kapat", au.Trigger(), au.Action(kind="power", power=False), lights=[cfg_a.device_id]))
        page.rows[power_off.id].run_button.click()

        selected_calls = created[cfg_a.device_id].calls
        scene = next(c[1] for c in selected_calls if c[0] == "send")
        assert scene[0] == (cfg_a.dps["switch_led"], DataPointType.BOOLEAN, True)  # film: ışığı aç
        assert (cfg_a.dps["work_mode"], DataPointType.ENUM, 1) in scene  # renk modu
        assert ("power", False) in selected_calls  # ikinci kural yalnızca seçili ışığa
        assert len(temporary) == 1 and temporary[0].cfg.device_id == cfg_b.device_id
        assert any(c[0] == "send" for c in temporary[0].calls) and ("power", False) not in temporary[0].calls
        assert bridge.cfg.device_id == cfg_a.device_id  # köprü hiç başka ışığa geçmedi
        assert page.rows[everywhere.id].last_label.text() == "Son çalışma: başarılı"
    finally:
        win.close()
        bridge.shutdown()


# =============================== alt bilgi, duraklatma, dil ===============================


def test_footer_states_the_limits_plainly_and_flags_the_feature_as_unverified(ui):
    win, page, host, backend, _ = ui
    body = page.limits_label.text()
    for phrase in ("uygulama çalışırken", "uyanıkken", "Bluetooth menzilindeyken", "Smart Life", "3 kez", "tepsisinden"):
        assert phrase in body, phrase
    assert page.unverified_label.text() == "Deneysel: bu özellik gerçek cihazda henüz doğrulanmadı."


def test_tolerance_setting_persists(ui):
    win, page, host, backend, _ = ui
    assert page.tolerance_spin.value() == 10
    page.tolerance_spin.setValue(25)
    assert host.store.tolerance_min == 25 and host.scheduler.store.tolerance_min == 25
    assert au.RuleStore.load(host.store.path).tolerance_min == 25


def test_pause_button_banner_and_row_status(ui):
    win, page, host, backend, _ = ui
    win.show()
    rule = add_sample(host)
    assert page.paused_banner.isHidden() and page.pause_button.text() == "Otomasyonları duraklat"
    page.pause_button.click()
    assert host.scheduler.paused and not page.paused_banner.isHidden()
    assert page.pause_button.text() == "Devam ettir" and page.rows[rule.id].status_label.text() == "Duraklatıldı"
    page.pause_button.click()
    assert not host.scheduler.paused and page.paused_banner.isHidden()


def test_renaming_a_light_updates_the_rule_summaries(ui):
    win, page, host, backend, _ = ui
    rule = host.add_rule(make_rule("Salon kuralı", lights=[A.device_id]))
    assert page.rows[rule.id].targets_label.text() == "Salon"
    renamed = lc.Config(**{**A.__dict__, "name": "Oturma odası"})
    win.set_devices([renamed, B], renamed.device_id)
    assert page.rows[rule.id].targets_label.text() == "Oturma odası"


def test_english_interface(qapp, tmp_path):
    i18n.set_language("en")
    host = AutomationHost(au.RuleStore(), au.EngineState(), FakeBackend(), submit=lambda c: asyncio.run(c))
    win = MainWindow(A, FakeBridge(), settings=QSettings(str(tmp_path / "e.ini"), QSettings.Format.IniFormat), use_tray=False, preset_store=PresetStore(), automation_host=host)
    try:
        assert win.tab_automation.text() == "Automation" and win.automation_page.empty_add_button.text() == "Add your first automation"
        rule = host.add_rule(make_rule("Evening", au.Trigger(kind="sun", event="sunrise", offset=15, lat=51.5, lon=-0.1, days=[5, 6]), au.Action(kind="power", power=True), all_lights=True))
        row = win.automation_page.rows[rule.id]
        assert row.summary_label.text() == "Weekends, 15 min after sunrise → turn the light on" and row.targets_label.text() == "All lights"
        assert "while the app is running" in win.automation_page.limits_label.text()
    finally:
        win.close()


# =============================== özet metinleri ===============================


def test_summary_texts_in_both_languages():
    rule = make_rule(
        "x",
        au.Trigger(kind="time", time="22:15", days=[0, 3, 6]),
        au.Action(kind="colour", bright=45, hue=0, sat=1000, fade_min=30),
        all_lights=True,
    )
    lookup = {"movie": "Film"}.get
    assert txt.summary_text(rule, lookup) == "Pzt, Per, Paz 22:15 → renk #FF0000, parlaklık %45, 30 dk'da yumuşak geçişle"
    missing = make_rule("y", au.Trigger(kind="startup"), au.Action(kind="preset", preset="u-gone"))
    assert txt.summary_text(missing, lookup) == "Uygulama açıldığında → hazır ayar (silinmiş)"
    assert txt.days_text([0, 1, 2, 3, 4, 5, 6]) == "Her gün" and txt.days_text([5, 6]) == "Hafta sonu"
    i18n.set_language("en")
    assert txt.summary_text(rule, lookup) == "Mon, Thu, Sun 22:15 → colour #FF0000, brightness 45%, with a 30-minute fade"
    assert txt.summary_text(missing, lookup) == "When the app starts → preset (deleted)"


def test_sun_phrases_before_at_and_after():
    base = dict(kind="sun", lat=41.0, lon=29.0)
    assert txt.trigger_text(au.Trigger(event="sunrise", offset=0, **base)) == "Her gün, gün doğumunda"
    assert txt.trigger_text(au.Trigger(event="sunrise", offset=-20, **base)) == "Her gün, gün doğumundan 20 dk önce"
    assert txt.trigger_text(au.Trigger(event="sunset", offset=45, **base)) == "Her gün, gün batımından 45 dk sonra"


def test_next_and_last_texts():
    zone = FixedZone(3)
    now = 1_790_000_000.0
    assert txt.next_text(None, now, zone) == "Planlı çalışma yok"
    assert txt.next_text(now + 3600, now, zone).startswith("Sonraki: bugün") or txt.next_text(now + 3600, now, zone).startswith("Sonraki: yarın")
    assert txt.next_text(now + 3 * 86400, now, zone).split()[1] in {"Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"}
    assert txt.last_text(None) == ""
    assert txt.last_text(au.Result("r", "n", "l", "n", "interrupted")) == "Son geçiş elle durduruldu"
    assert txt.last_text(au.Result("r", "n", "l", "n", "failed", "preset_missing")).endswith("silinmiş")


def test_every_rule_error_code_has_a_message_in_both_languages():
    codes = ["name", "trigger", "time", "days", "sun_event", "coords", "offset", "action", "bright", "temp", "hue", "sat", "preset", "fade", "fade_kind", "target", "limit", "unknown", "rule", "tolerance"]
    for language in ("tr", "en"):
        i18n.set_language(language)
        for code in codes:
            text = txt.error_text(au.RuleError(code))
            assert text and not text.startswith("automation.error_"), (language, code)
