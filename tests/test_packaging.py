"""Paketleme: sürüm bilgisi, yükleyici betiği, release iş akışı ve --minimized (derleme gerektirmez)."""

from __future__ import annotations

import re
from pathlib import Path

import devices
import version
from light_app import start_hidden

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_version_info_is_complete_and_file_names_are_ascii():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.__version__)
    for value in (version.APP_SLUG, version.DATA_FOLDER, version.__version__):
        assert re.fullmatch(r"[A-Za-z0-9._-]+", value), value  # dosya adlarında Türkçe karakter olmasın
    assert version.APP_NAME.strip() and version.APP_URL.startswith("https://")
    assert devices.user_data_dir().name == version.DATA_FOLDER


def test_ps_scripts_can_read_every_key_from_version_py():
    info = read("installer/app_info.ps1")
    for key in ("__version__", "APP_NAME", "APP_SLUG", "DATA_FOLDER", "APP_AUTHOR", "APP_URL"):
        assert f'"{key}"' in info and re.search(rf"(?m)^{key}\s*=\s*\"", read("version.py")), key


def test_installer_script_has_the_promised_features():
    iss = read("installer/setup.iss")
    assert "OutputBaseFilename={#AppSlug}-Setup-{#AppVersion}" in iss
    assert "PrivilegesRequired=lowest" in iss  # yönetici yetkisi gerekmez
    assert "{autoprograms}" in iss and "{autodesktop}" in iss and "Tasks: desktopicon" in iss
    assert "Tasks: startup" in iss and "--minimized" in iss and "uninsdeletevalue" in iss
    assert "ShowLanguageDialog=no" in iss and "Turkish.isl" in iss and "Default.isl" in iss
    assert "{#DataFolder}" in iss and "MB_DEFBUTTON2" in iss  # kaldırırken veri varsayılan olarak silinmez
    assert read("installer/setup.iss").count("[Setup]") == 1


def test_release_workflow_builds_installer_zip_and_checksums():
    workflow = read(".github/workflows/release.yml")
    for step in ("./build_exe.ps1", "./installer/build_installer.ps1", "./installer/package_release.ps1", "release-assets/*"):
        assert step in workflow
    assert "body_path: .github/release_body.md" in workflow
    assert workflow.index("build_exe.ps1") < workflow.index("build_installer.ps1") < workflow.index("package_release.ps1")
    package = read("installer/package_release.ps1")
    assert "-Setup-" in package and "-portable-" in package and "SHA256SUMS.txt" in package


def test_release_notes_explain_install_in_both_languages_and_flag_unverified_features():
    body = read(".github/release_body.md")
    assert "How to install" in body and "Nasıl kurulur" in body
    assert "More info" in body and "Yine de çalıştır" in body and "code-signed" in body and "kod imzalı" in body
    flat = re.sub(r"[>*\s]+", " ", body)  # satır sonları ve biçimlendirme işaretlerini yok say
    assert "not yet been verified" in flat and "doğrulanmadı" in flat


def test_start_hidden_only_when_minimized_and_a_tray_exists():
    assert start_hidden(["app", "--minimized"], True) is True
    assert start_hidden(["app", "--minimized"], False) is False  # tepsi yoksa pencere yine de görünmeli
    assert start_hidden(["app"], True) is False
