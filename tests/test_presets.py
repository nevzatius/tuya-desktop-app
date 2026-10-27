"""Kullanıcının kendi hazır ayarları: depo (kayıt/düzenleme/silme/bozuk dosya) ve ana ekran arayüzü."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QObject, QSettings, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import light_core as lc  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.presets import MAX_NAME, MAX_USER_PRESETS, PRESETS, PresetError, PresetStore, name_key  # noqa: E402
from ui.presets_view import ManagePresetsDialog, PresetDialog, PresetsSection  # noqa: E402
from ui.theme import apply_theme  # noqa: E402

CFG = lc.Config(device_id="bf0123456789abcdefghij", local_key="TestKey#0123456!", uuid="0123456789abcdef", name="Test ışığı")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


# -- depo ----------------------------------------------------------------------------


def test_builtins_are_always_present_and_cannot_be_deleted_or_changed(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    assert [p.key for p in store.all()] == [p.key for p in PRESETS]
    for preset in PRESETS:
        assert preset.builtin
        with pytest.raises(PresetError) as err:
            store.delete(preset.key)
        assert err.value.code == "builtin"
        with pytest.raises(PresetError) as err:
            store.update(preset.key, "Yeni ad", "white", 50)
        assert err.value.code == "builtin"
    assert len(store.all()) == len(PRESETS)


def test_add_edit_delete_roundtrip_through_the_file(tmp_path):
    path = tmp_path / "presets.json"
    store = PresetStore(path)
    desk = store.add("  Çalışma   masası ", "white", 70, temp=60)
    night = store.add("Gece okuma", "colour", 15, hue=30, sat=800)
    assert desk.name == "Çalışma masası" and not desk.builtin and desk.key.startswith("u-")

    loaded = PresetStore.load(path)
    assert [p.name for p in loaded.user_presets()] == ["Çalışma masası", "Gece okuma"]
    assert loaded.get(night.key).hue == 30 and loaded.get(desk.key).temp == 60

    edited = loaded.update(desk.key, "Masa", "colour", 40, hue=200, sat=500)
    assert (edited.name, edited.mode, edited.bright, edited.hue) == ("Masa", "colour", 40, 200)
    assert edited.key == desk.key  # kimlik değişmez (otomasyonlar buna bağlı)
    assert PresetStore.load(path).get(desk.key).name == "Masa"

    loaded.delete(night.key)
    assert [p.name for p in PresetStore.load(path).user_presets()] == ["Masa"]
    with pytest.raises(PresetError) as err:
        loaded.delete(night.key)
    assert err.value.code == "unknown"


def test_builtins_can_be_hidden_and_shown_again(tmp_path):
    path = tmp_path / "presets.json"
    store = PresetStore(path)
    store.set_hidden("movie", True)
    assert "movie" not in [p.key for p in store.visible()] and store.get("movie") is not None
    assert "movie" not in [p.key for p in PresetStore.load(path).visible()]  # kalıcı
    store.set_hidden("movie", False)
    assert "movie" in [p.key for p in PresetStore.load(path).visible()]
    with pytest.raises(PresetError):
        store.set_hidden("u-nonexistent", True)


def test_name_validation(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    for bad, code in (("", "empty"), ("   ", "empty"), ("x" * (MAX_NAME + 1), "too_long"), ("film", "duplicate"), ("OKUMA", "duplicate")):
        with pytest.raises(PresetError) as err:
            store.add(bad, "white", 50)
        assert err.value.code == code, bad
    store.add("Lamba", "white", 50)
    with pytest.raises(PresetError) as err:
        store.add("lamba", "white", 50)  # büyük/küçük harf fark etmez
    assert err.value.code == "duplicate"
    other = store.add("Diğer", "white", 50)
    with pytest.raises(PresetError):
        store.update(other.key, "Lamba", "white", 50)
    store.update(other.key, "Diğer", "white", 60)  # kendi adını korumak çakışma sayılmaz


def test_values_are_validated_and_clamped(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    with pytest.raises(PresetError) as err:
        store.add("Garip", "disco", 50)
    assert err.value.code == "values"
    preset = store.add("Sınırlar", "colour", 500, temp=-5, hue=999, sat=99999)
    assert (preset.bright, preset.temp, preset.hue, preset.sat) == (100, 0, 360, 1000)


def test_user_preset_limit(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    for index in range(MAX_USER_PRESETS):
        store.add(f"Ayar {index}", "white", 50)
    with pytest.raises(PresetError) as err:
        store.add("Fazla", "white", 50)
    assert err.value.code == "limit"


def test_find_by_name_or_key_is_case_insensitive_and_sees_hidden_builtins(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    mine = store.add("Çalışma", "white", 60)
    store.set_hidden("movie", True)
    assert store.find("film").key == "movie" and store.find("MOVIE").key == "movie"
    assert store.find(" çalışma ").key == mine.key and store.find(mine.key).key == mine.key
    assert store.find("yok böyle") is None and store.find("") is None


def test_find_survives_turkish_upper_and_lower_case(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    desk = store.add("Çalışma masası", "white", 60)
    lamp = store.add("İlk Işık", "white", 50)
    assert store.find("ÇALIŞMA MASASI").key == desk.key and store.find("çalışma masası").key == desk.key
    assert store.find("ÇALIŞMA MASASI") is store.find("Çalışma Masası")
    assert store.find("İLK IŞIK").key == lamp.key and store.find("ilk ışık").key == lamp.key
    assert store.find("ILK ISIK") is None  # ş/ı ayrımı yok sayılmaz, yalnızca i/ı/İ/I birleşir
    assert store.find("FİLM").key == "movie" and store.find("FILM").key == "movie"
    assert name_key("İlk") == name_key("İlk")  # ayrık İ


def test_names_differing_only_in_turkish_case_count_as_duplicates(tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    store.add("Işık", "white", 60)
    with pytest.raises(PresetError) as err:
        store.add("IŞIK", "white", 60)
    assert err.value.code == "duplicate"


def test_the_file_holds_no_secrets(tmp_path):
    path = tmp_path / "presets.json"
    store = PresetStore(path)
    store.add("Lamba", "white", 50)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert set(data) == {"version", "hidden", "hotkeys", "presets"}
    for forbidden in ("local_key", "device_id", "uuid", "address", "secret"):
        assert forbidden not in text


def test_memory_store_never_touches_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = PresetStore()  # yol yok
    store.add("Bellekte", "white", 50)
    store.set_hidden("night", True)
    assert list(tmp_path.iterdir()) == []


# -- bozuk dosya ----------------------------------------------------------------------


@pytest.mark.parametrize("content", ["{bozuk json", "", "[1, 2, 3]", "null-degil", '"sadece metin"'])
def test_corrupt_file_is_backed_up_and_the_app_starts_with_builtins(tmp_path, content):
    path = tmp_path / "presets.json"
    path.write_text(content, encoding="utf-8")
    store = PresetStore.load(path)
    assert store.problem and store.recovered_from is not None and store.recovered_from.exists()
    assert store.recovered_from.read_text(encoding="utf-8") == content  # yedek özgün içeriği taşır
    assert [p.key for p in store.visible()] == [p.key for p in PRESETS]
    store.add("Yeni", "white", 50)  # bozuk dosya sonrası yazmak çalışır
    assert [p.name for p in PresetStore.load(path).user_presets()] == ["Yeni"]


def test_invalid_entries_are_skipped_but_valid_ones_survive_with_a_backup(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "hidden": ["movie", "u-x", 5],
                "presets": [
                    {"id": "u-aaaa1111", "name": "İyi", "mode": "white", "bright": 40, "temp": 20},
                    {"id": "u-bbbb2222", "name": "", "mode": "white", "bright": 40},
                    {"id": "reading", "name": "Taklit", "mode": "white", "bright": 40},
                    {"id": "u-cccc3333", "name": "Garip mod", "mode": "disco", "bright": 40},
                    {"id": "u-aaaa1111", "name": "Aynı kimlik", "mode": "white", "bright": 40},
                    "bir metin",
                ],
            }
        ),
        encoding="utf-8",
    )
    store = PresetStore.load(path)
    assert [p.name for p in store.user_presets()] == ["İyi"]
    assert store.is_hidden("movie") and not store.is_hidden("u-x")  # bilinmeyen gizli anahtar atlanır
    assert store.problem and store.recovered_from is not None


def test_missing_file_is_a_normal_first_start(tmp_path):
    store = PresetStore.load(tmp_path / "presets.json")
    assert not store.problem and store.recovered_from is None and store.user_presets() == []


def test_user_preset_with_a_builtin_name_from_another_language_still_loads(tmp_path):
    # İngilizce arayüzde "Okuma" serbesttir; Türkçeye geçince yerleşik "Okuma" ile aynı ad olur ve kaybolmamalı.
    path = tmp_path / "presets.json"
    path.write_text(json.dumps({"version": 1, "presets": [{"id": "u-12345678", "name": "Okuma", "mode": "white", "bright": 50}]}), encoding="utf-8")
    store = PresetStore.load(path)
    assert [p.name for p in store.user_presets()] == ["Okuma"] and not store.problem


# -- arayüz ----------------------------------------------------------------------------


class FakeBridge(QObject):
    state = Signal(object)
    status = Signal(str)
    error = Signal(str)
    problem = Signal(str)
    log = Signal(str)
    connectedChanged = Signal(bool)

    def __init__(self):
        super().__init__()
        self.scenes = []

    def apply_scene(self, preset):
        self.scenes.append(preset.name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None


@pytest.fixture()
def window(qapp, tmp_path):
    store = PresetStore(tmp_path / "presets.json")
    bridge = FakeBridge()
    win = MainWindow(CFG, bridge, settings=QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat), use_tray=False, preset_store=store)
    win.resize(430, 900)
    yield win, bridge, store
    win.close()


def fill_dialog(monkeypatch, name, **values):
    """PresetDialog.exec() kullanıcı gibi davranır: adı yazar, değerleri ayarlar, Kaydet'e basar."""

    def fake_exec(self):
        self.name_edit.setText(name)
        if values:
            self.editor.set_values(**values)
        self.save_button.click()
        return QDialog.DialogCode.Accepted if self.result_preset is not None else QDialog.DialogCode.Rejected

    monkeypatch.setattr(PresetDialog, "exec", fake_exec)


def test_chips_show_builtin_and_user_presets(window):
    win, bridge, store = window
    assert [b.text() for b in win.preset_buttons] == ["Okuma", "Odak", "Gece", "Film", "Romantik", "Okyanus"]
    store.add("Çalışma masası", "white", 70, temp=60)
    win.presets_section.refresh()
    assert [b.text() for b in win.preset_buttons][-1] == "Çalışma masası" and len(win.preset_buttons) == 7


def test_clicking_a_user_chip_applies_it_in_one_command_and_updates_controls(window):
    win, bridge, store = window
    mine = store.add("Mavi köşe", "colour", 33, hue=240, sat=900)
    win.presets_section.refresh()
    next(b for b in win.preset_buttons if b.property("presetKey") == mine.key).click()
    assert bridge.scenes == ["Mavi köşe"]
    assert win.bright.value() == 33 and win.wheel.hs() == (240, 900) and win.stack.currentIndex() == 1


def test_save_current_state_uses_the_screen_values_and_adds_a_chip(window, monkeypatch):
    win, bridge, store = window
    win.bright.setValue(42)
    win.temp.setValue(77)
    fill_dialog(monkeypatch, "Salon akşam")  # değerlere dokunma: ekrandakiler kaydedilmeli
    assert win.presets_section.save_current()
    saved = store.find("Salon akşam")
    assert (saved.mode, saved.bright, saved.temp) == ("white", 42, 77)
    assert "Salon akşam" in [b.text() for b in win.preset_buttons]
    assert PresetStore.load(store.path).find("Salon akşam") is not None


def test_save_dialog_shows_a_clear_error_and_stays_open_on_duplicate_or_empty(window):
    win, bridge, store = window
    dialog = PresetDialog(store, None, win.current_scene(), win)
    dialog.name_edit.setText("film")
    dialog.save_button.click()
    assert dialog.result_preset is None and not dialog.error.isHidden()
    assert "zaten var" in dialog.error.text()
    dialog.name_edit.setText("")
    dialog.save_button.click()
    assert "ad yazın" in dialog.error.text()
    dialog.name_edit.setText("Benzersiz")
    dialog.save_button.click()
    assert dialog.result_preset is not None and store.find("Benzersiz") is not None


def test_edit_changes_name_and_values_and_builtins_cannot_be_edited(window, monkeypatch):
    win, bridge, store = window
    mine = store.add("Eski ad", "white", 30, temp=10)
    win.presets_section.refresh()
    fill_dialog(monkeypatch, "Yeni ad", mode="colour", bright=55, hue=100, sat=700)
    assert win.presets_section.edit(mine.key)
    edited = store.get(mine.key)
    assert (edited.name, edited.mode, edited.bright, edited.hue) == ("Yeni ad", "colour", 55, 100)
    assert "Yeni ad" in [b.text() for b in win.preset_buttons] and "Eski ad" not in [b.text() for b in win.preset_buttons]
    assert not win.presets_section.edit("reading")  # yerleşik: düzenlenmez


def test_delete_asks_first_and_builtins_are_never_deleted(window):
    win, bridge, store = window
    section = win.presets_section
    mine = store.add("Silinecek", "white", 30)
    section.refresh()
    asked = []
    section._confirm = lambda parent, text: asked.append(text) or False
    assert not section.delete(mine.key) and store.get(mine.key) is not None and "Silinecek" in asked[0]
    section._confirm = lambda parent, text: True
    assert section.delete(mine.key) and store.get(mine.key) is None
    assert "Silinecek" not in [b.text() for b in win.preset_buttons]
    assert not section.delete("reading") and store.get("reading") is not None


def test_hiding_a_builtin_removes_its_chip_and_showing_brings_it_back(window):
    win, bridge, store = window
    section = win.presets_section
    seen = []
    section.changed.connect(lambda: seen.append(1))
    assert section.toggle_hidden("movie")
    assert "Film" not in [b.text() for b in win.preset_buttons] and len(win.preset_buttons) == 5
    assert section.toggle_hidden("movie") and "Film" in [b.text() for b in win.preset_buttons]
    assert len(seen) == 2


def test_chip_context_menu_offers_the_right_actions(window):
    win, bridge, store = window
    mine = store.add("Benim", "white", 30)
    section = win.presets_section
    builtin_menu = section.chip_menu(store.get("reading"))
    user_menu = section.chip_menu(mine)
    assert [a.text() for a in builtin_menu.actions()] == ["Gizle"]
    assert [a.text() for a in user_menu.actions()] == ["Düzenle…", "Sil"]


def test_many_presets_scroll_instead_of_growing_forever(window, qapp):
    win, bridge, store = window
    win.show()
    section = win.presets_section
    section.refresh()
    few = section.scroll.height()
    for index in range(20):
        store.add(f"Ayar {index}", "white", 50)
    section.refresh()
    assert len(win.preset_buttons) == 26
    assert section.scroll.height() > few
    row = win.preset_buttons[0].height()
    assert section.scroll.height() <= 4 * row + 3 * 10 + 2  # en çok 4 satır görünür, kalanı kaydırılır
    for _ in range(3):  # silinen eski çipler ve yeni düzen birkaç olay turunda oturur
        qapp.processEvents()
    assert section.scroll.verticalScrollBar().maximum() > 0


def test_manage_dialog_lists_tags_and_drives_the_same_actions(window, qapp):
    win, bridge, store = window
    mine = store.add("Benim", "white", 30)
    store.set_hidden("night", True)
    win.presets_section.refresh()
    dialog = ManagePresetsDialog(win.presets_section, win)
    texts = [dialog.list.item(i).text() for i in range(dialog.list.count())]
    assert any(t.startswith("Gece") and "yerleşik" in t and "gizli" in t for t in texts)
    assert any(t == "Benim" for t in texts)

    def select(key):
        for i in range(dialog.list.count()):
            if dialog.list.item(i).data(0x0100) == key:
                dialog.list.setCurrentRow(i)

    select("reading")
    assert not dialog.edit_button.isEnabled() and not dialog.delete_button.isEnabled() and dialog.hide_button.isEnabled()
    assert dialog.hide_button.text() == "Gizle"
    select("night")
    assert dialog.hide_button.text() == "Göster"
    dialog.hide_button.click()
    assert not store.is_hidden("night")
    select(mine.key)
    assert dialog.edit_button.isEnabled() and dialog.delete_button.isEnabled() and not dialog.hide_button.isEnabled()
    win.presets_section._confirm = lambda parent, text: True
    dialog.delete_button.click()
    assert store.get(mine.key) is None and all(dialog.list.item(i).data(0x0100) != mine.key for i in range(dialog.list.count()))


def test_current_scene_reports_what_the_screen_shows(window):
    win, bridge, store = window
    win.bright.setValue(61)
    win.seg_colour.click()
    win.wheel.set_hs(123, 456)
    assert win.current_scene() == {"mode": "colour", "bright": 61, "temp": win.temp.value(), "hue": 123, "sat": 456}


def test_main_window_without_a_store_uses_memory_only(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    win = MainWindow(CFG, FakeBridge(), settings=QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat), use_tray=False)
    win.preset_store.add("Geçici", "white", 50)
    win.close()
    assert not (tmp_path / "appdata").exists()
