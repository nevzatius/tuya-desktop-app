"""Kurulum sihirbazı v2: adımlar, pano algılama, canlı doğrulama, hata kurtarma, tarama, başarı ekranı."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

import cloud_import as ci  # noqa: E402
import i18n  # noqa: E402
from test_multi import ID, SECRET, found  # noqa: E402,F401
from test_ui import qapp, wait_for  # noqa: E402,F401
from ui.setup_dialog import (  # noqa: E402
    PAGE_ACCOUNT,
    PAGE_CREDENTIALS,
    PAGE_DONE,
    PAGE_LIGHTS,
    PAGE_MANUAL,
    PAGE_WELCOME,
    TUYA_URL,
    SetupDialog,
    signal_text,
)


def make_dialog(fetcher=None, existing=None, scanner=None):
    opened: list[str] = []
    d = SetupDialog(
        existing or set(),
        fetcher=fetcher or (lambda a, s, r: ([found(1)], r)),
        scanner=scanner or (lambda: []),
        open_url=opened.append,
    )
    d.opened = opened
    return d


def fill(d, access_id=ID, secret=SECRET):
    d.access_id.setText(access_id)
    d.secret.setText(secret)


def reach_lights(d, devices=None):
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d)
    d.find_button.click()
    assert wait_for(lambda: d.stack.currentIndex() == PAGE_LIGHTS)
    assert wait_for(lambda: d._worker is None)


# -- adımlar ve gezinme ---------------------------------------------------------------


def test_flow_and_step_indicator(qapp):
    d = make_dialog()
    assert d.stack.currentIndex() == PAGE_WELCOME and d.step_label.text() == "Adım 1 / 4"
    d.start_button.click()
    assert d.stack.currentIndex() == PAGE_ACCOUNT and d.step_label.text() == "Adım 2 / 4" and d.indicator.current == 2
    d.account_next.click()
    assert d.stack.currentIndex() == PAGE_CREDENTIALS and d.step_label.text() == "Adım 3 / 4"
    reach_lights(d)
    assert d.step_label.text() == "Adım 4 / 4" and d.indicator.current == 4
    d.stack.setCurrentIndex(PAGE_MANUAL)  # ileri düzey sayfada adım göstergesi yok
    assert d.step_label.isHidden() and d.indicator.isHidden()


def test_step_label_in_english(qapp):
    i18n.set_language("en")
    d = make_dialog()
    assert d.step_label.text() == "Step 1 / 4" and d.start_button.text() == "Get started"


def test_existing_user_skips_intro_pages(qapp):
    d = make_dialog(existing={"dev9"})
    assert d.stack.currentIndex() == PAGE_CREDENTIALS and d.step_label.text() == "Adım 3 / 4"


def test_cancel_rejects(qapp):
    d = make_dialog()
    d.cancel_button.click()
    assert d.result() == QDialog.DialogCode.Rejected and d.added_devices() == []


def test_every_instruction_step_has_an_open_browser_button(qapp):
    d = make_dialog()
    assert len(d.open_buttons) == 4
    for button in d.open_buttons:
        button.click()
    assert d.opened == [TUYA_URL] * 4 and TUYA_URL == "https://iot.tuya.com"


# -- pano algılama ve canlı doğrulama ---------------------------------------------------


def test_clipboard_detection_fills_empty_boxes_only(qapp):
    d = make_dialog()
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    assert d.apply_clipboard_text(f"  {ID}\n") == "id" and d.access_id.text() == ID
    assert "panodan" in d.paste_note.text() and not d.paste_note.isHidden()
    assert d.apply_clipboard_text("c" * 20) is None and d.access_id.text() == ID  # dolu kutunun üstüne yazmaz
    assert d.apply_clipboard_text(SECRET) == "secret" and d.secret.text() == SECRET
    d2 = make_dialog()
    for noise in ("", "merhaba dünya bu bir cümle", "a" * 19, "a" * 33, "abc-defghijklmnopqrst", "x y " * 8):
        assert d2.apply_clipboard_text(noise) is None
    assert d2.access_id.text() == "" and d2.secret.text() == ""


def test_clipboard_signal_only_acts_on_credentials_page(qapp):
    d = make_dialog()
    clipboard = QApplication.clipboard()
    clipboard.setText(ID)
    qapp.processEvents()
    assert d.access_id.text() == ""  # 1. adımdayken pano okunmaz
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    clipboard.setText(SECRET)
    qapp.processEvents()
    assert d.secret.text() == SECRET
    clipboard.clear()


def test_live_validation_cleans_whitespace_and_shows_length(qapp):
    d = make_dialog()
    d.access_id.setText("aaaa bbbb​cccc")
    assert d.access_id.text() == "aaaabbbbcccc" and d.id_status.text() == "12 / 20"
    d.access_id.setText(ID)
    assert d.id_status.text() == "✓ 20 / 20"
    d.access_id.setText("")
    assert d.id_status.text() == ""
    d.secret.setText(" " + SECRET + " ")
    assert d.secret.text() == SECRET and d.secret_status.text().startswith("✓")


# -- bulut ------------------------------------------------------------------------------


def test_cloud_validation_blocks_fetch(qapp):
    calls = []
    d = make_dialog(lambda a, s, r: calls.append(1) or ([], r))
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d, "kisa")
    d.find_button.click()
    assert "20" in d.cloud_message.text() and not d.cloud_message.isHidden()
    assert calls == [] and d._worker is None


def test_region_is_automatic_with_advanced_override(qapp):
    seen = []
    d = make_dialog(lambda a, s, r: seen.append(r) or ([found(1)], r))
    assert d.advanced_box.isHidden() and d.region.currentData() == ""
    d._auto_region = "eu"
    reach_lights(d)
    assert seen == ["eu"]
    d.advanced_toggle.setChecked(True)
    assert not d.advanced_box.isHidden()
    d.region.setCurrentIndex(d.region.findData("us"))
    assert d.selected_region() == "us"


def test_region_guess():
    assert ci.guess_region("tr_TR") == "eu" and ci.guess_region("en_US") == "us" and ci.guess_region("en-IN") == "in"
    assert ci.guess_region("zh_CN") == "cn" and ci.guess_region("ja_JP") == "sg" and ci.guess_region(None) == "eu"


def test_cloud_success_lists_names_and_adds_checked(qapp):
    devices = [found(1), found(2), found(3, light=False)]
    d = make_dialog(lambda a, s, r: (devices, r), existing={"dev2"})
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d)
    d.find_button.click()
    assert wait_for(lambda: d.stack.currentIndex() == PAGE_LIGHTS)
    assert d.secret.text() == ""  # Secret temizlendi
    rows = d.rows
    assert [r.check.isChecked() for r in rows] == [True, False, False]  # ekli olan ve ışık olmayan işaretsiz
    assert "zaten ekli" in rows[1].status.text() and "ışık değil" in rows[2].status.text()
    assert wait_for(lambda: d._worker is None and d.find_button.isEnabled())
    rows[0].name_edit.setText("  Oturma odası ")
    d.add_button.click()
    assert d.stack.currentIndex() == PAGE_DONE and d.result() != QDialog.DialogCode.Accepted
    assert "Oturma odası" in d.done_label.text()
    d.finish_button.click()
    assert d.result() == QDialog.DialogCode.Accepted
    assert [(c.device_id, c.name) for c in d.added_devices()] == [("dev1", "Oturma odası")]


def test_empty_name_keeps_original_name(qapp):
    d = make_dialog()
    reach_lights(d)
    d.rows[0].name_edit.setText("   ")
    d.add_button.click()
    assert d.added_devices()[0].name == "Işık 1"


def test_closing_on_done_page_keeps_added_lights(qapp):
    d = make_dialog()
    reach_lights(d)
    d.add_button.click()
    d.reject()  # pencereyi kapatmak
    assert d.result() == QDialog.DialogCode.Accepted and len(d.added_devices()) == 1


def test_secret_is_removed_from_clipboard_after_success(qapp):
    d = make_dialog()
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    QApplication.clipboard().setText(SECRET)
    qapp.processEvents()
    assert d.secret.text() == SECRET
    fill(d, ID, SECRET)
    d.find_button.click()
    assert wait_for(lambda: d.stack.currentIndex() == PAGE_LIGHTS)
    assert QApplication.clipboard().text() == ""
    QApplication.clipboard().setText("başka bir şey")  # alakasız pano içeriğine dokunulmaz
    d._submitted_secret = ""
    d._fetch_done(([found(1)], "eu"))
    assert QApplication.clipboard().text() == "başka bir şey"
    QApplication.clipboard().clear()


@pytest.mark.parametrize(
    ("error", "kind", "open_visible"),
    [
        ("Access ID veya Secret yanlış", "credentials", True),
        ("Yetki yok", "permission", True),
        ("Cihaz yok", "no_devices", True),
        ("İnternete ulaşılamadı", "network", False),
    ],
)
def test_cloud_failure_offers_retry_and_context_button(qapp, error, kind, open_visible):
    attempts = []

    def flaky(a, s, r):
        attempts.append(1)
        if len(attempts) == 1:
            raise ci.CloudError(error, kind)
        return [found(1)], r

    d = make_dialog(flaky)
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d)
    d.find_button.click()
    assert wait_for(lambda: error in d.cloud_message.text())
    assert wait_for(lambda: d.find_button.isEnabled())
    assert not d.retry_button.isHidden() and d.open_tuya_button.isHidden() is (not open_visible)
    assert d.secret.text() == SECRET  # düzeltip tekrar denemek için korunur
    d.retry_button.click()
    assert wait_for(lambda: d.stack.currentIndex() == PAGE_LIGHTS) and len(attempts) == 2
    assert d.retry_button.isHidden()


def test_open_tuya_button_after_error_opens_site(qapp):
    d = make_dialog(lambda a, s, r: (_ for _ in ()).throw(ci.CloudError("x", "credentials")))
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d)
    d.find_button.click()
    assert wait_for(lambda: not d.open_tuya_button.isHidden())
    d.open_tuya_button.click()
    assert d.opened == [TUYA_URL]


def test_cloud_unexpected_exception_is_reported(qapp):
    d = make_dialog(lambda a, s, r: 1 / 0)
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    fill(d)
    d.find_button.click()
    assert wait_for(lambda: "Beklenmeyen hata" in d.cloud_message.text())
    assert not d.retry_button.isHidden()


def test_results_requires_a_selection_and_flags_experimental(qapp):
    d = make_dialog(lambda a, s, r: ([found(1, standard=False)], r))
    reach_lights(d)
    row = d.rows[0]
    assert "deneysel" in row.status.text() and "Deneysel" in d.results_note.text()
    row.check.setChecked(False)
    d.add_button.click()
    assert "en az bir" in d.results_note.text() and d.stack.currentIndex() == PAGE_LIGHTS


# -- yakın tarama -----------------------------------------------------------------------


def nearby(uuid, rssi):
    return SimpleNamespace(uuid=uuid, rssi=rssi)


def test_signal_text():
    assert signal_text(-50) == "güçlü" and signal_text(-70) == "iyi" and signal_text(-90) == "zayıf" and signal_text(None) == "zayıf"


def test_scan_marks_nearby_lights_with_signal(qapp):
    d = make_dialog(
        lambda a, s, r: ([found(1), found(2), found(3, light=False)], r),
        scanner=lambda: [nearby("u1", -55), nearby("zzz", -80)],
    )
    reach_lights(d)
    d.scan_button.click()
    assert wait_for(lambda: d._scan_worker is None and d.scan_button.isEnabled())
    rows = d.rows
    assert "yakında" in rows[0].status.text() and "güçlü" in rows[0].status.text()
    assert "yakında görünmedi" in rows[1].status.text()
    assert "yakında" not in rows[2].status.text()  # ışık olmayan cihaz taranmaz
    assert "2" in d.scan_note.text()


def test_scan_without_results_and_with_failure(qapp):
    d = make_dialog(scanner=lambda: [])
    reach_lights(d)
    d.scan_button.click()
    assert wait_for(lambda: "bulunamadı" in d.scan_note.text())

    def boom():
        raise OSError("adaptör yok")

    d2 = make_dialog(scanner=boom)
    reach_lights(d2)
    d2.scan_button.click()
    assert wait_for(lambda: "Tarama başarısız" in d2.scan_note.text())
    assert wait_for(lambda: d2.scan_button.isEnabled())


# -- elle giriş (ileri düzey) ------------------------------------------------------------


def test_manual_entry_is_reachable_from_advanced_and_ends_on_done(qapp):
    d = make_dialog()
    d.stack.setCurrentIndex(PAGE_CREDENTIALS)
    d.manual_button.click()
    assert d.stack.currentIndex() == PAGE_MANUAL
    d.manual_add.click()
    assert not d.manual_message.isHidden() and d.added_devices() == []
    d.m_id.setText(" bf2a 2b17​ ")
    d.m_key.setText("TestKey#0123456!")
    d.m_uuid.setText("0123456789abcdef")
    d.manual_add.click()
    assert d.stack.currentIndex() == PAGE_DONE
    [c] = d.added_devices()
    assert (c.device_id, c.local_key, c.name) == ("bf2a2b17", "TestKey#0123456!", "Işık")


def test_secret_visibility_toggle(qapp):
    from PySide6.QtWidgets import QLineEdit

    d = make_dialog()
    assert d.secret.echoMode() == QLineEdit.EchoMode.Password
    d.show_secret.setChecked(True)
    assert d.secret.echoMode() == QLineEdit.EchoMode.Normal


def test_cloud_error_kinds():
    assert ci.classify("sign invalid") == "credentials" and ci.classify("code 1106 permission deny") == "permission"
    assert ci.classify("token invalid") == "token" and ci.classify("Connection timed out") == "network"
    assert ci.classify("???") == "other" and ci.classify("") == "other"
    with pytest.raises(ci.CloudError) as info:
        ci.fetch("kisa", "x", "eu")
    assert info.value.kind == "validation"
    with pytest.raises(ci.CloudError) as info:
        ci.connect(ID, SECRET, "eu", lambda **kw: SimpleNamespace(error="sign invalid"))
    assert info.value.kind == "credentials"
