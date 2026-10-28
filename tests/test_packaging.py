"""Paketleme: sürüm bilgisi, yükleyici betiği, release iş akışı ve --minimized (derleme gerektirmez)."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_package_script_writes_checksums_through_the_lf_helper():
    package = read("installer/package_release.ps1")
    assert "checksums.ps1" in package and "Write-Sha256Sums" in package
    assert "Set-Content" not in package  # Set-Content CRLF yazar
    helper = read("installer/checksums.ps1")
    assert "UTF8Encoding $false" in helper and "WriteAllText" in helper and "`n" in helper


@pytest.mark.skipif(shutil.which("powershell") is None and shutil.which("pwsh") is None, reason="PowerShell yok")
def test_sha256sums_has_lf_line_endings_no_bom_and_matches_the_files(tmp_path):
    out = tmp_path / "assets"
    out.mkdir()
    files = {"B-portable-1.0.0.zip": b"zip bytes", "A-Setup-1.0.0.exe": b"exe bytes" * 100}
    for name, data in files.items():
        (out / name).write_bytes(data)
    (out / "SHA256SUMS.txt").write_bytes(b"old\r\n")  # yeniden üretimde yok sayılır ve ezilir
    shell = shutil.which("pwsh") or shutil.which("powershell")
    command = f'. "{ROOT / "installer" / "checksums.ps1"}"; Write-Sha256Sums "{out}"'
    done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    raw = (out / "SHA256SUMS.txt").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and b"\r" not in raw
    assert raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    expected = [f"{hashlib.sha256(files[name]).hexdigest()}  {name}" for name in sorted(files)]  # ad sırasına göre
    assert raw.decode("ascii").splitlines() == expected


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


# -- iş akışı güvenliği ---------------------------------------------------------------------------


WORKFLOWS = (".github/workflows/ci.yml", ".github/workflows/release.yml")


def job_block(workflow: str, job: str) -> str:
    """`jobs:` altındaki iş (iki boşluk girintili ad) bir sonraki işe ya da dosya sonuna kadar."""
    match = re.search(rf"(?ms)^  {job}:\n(.*?)(?=^  \S+:\n|\Z)", workflow)
    assert match, job
    return match.group(1)


@pytest.mark.parametrize("path", WORKFLOWS)
def test_every_action_is_pinned_to_a_commit_sha_with_a_version_comment(path):
    uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S.*)$", read(path))
    assert uses
    for line in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+", line.strip()), line


@pytest.mark.parametrize("path", WORKFLOWS)
def test_checkout_does_not_keep_credentials(path):
    text = read(path)
    assert text.count("persist-credentials: false") == text.count("actions/checkout@")


def test_release_build_job_only_reads_and_only_the_tag_publish_job_writes():
    workflow = read(".github/workflows/release.yml")
    assert re.search(r"(?m)^permissions: \{\}$", workflow)  # varsayılan: hiçbir yetki
    build, publish = job_block(workflow, "build"), job_block(workflow, "publish")
    assert "contents: read" in build and "contents: write" not in build
    assert workflow.count("contents: write") == 1 and "contents: write" in publish
    assert "needs: build" in publish and "if: startsWith(github.ref, 'refs/tags/')" in publish
    assert "action-gh-release" in publish and "action-gh-release" not in build
    assert "upload-artifact" in build and "download-artifact" in publish
    assert "workflow_dispatch" in workflow  # elle çalıştırma yalnızca derler: yayın işi tag'e bağlı


def extract_tag_check(workflow: str) -> str:
    match = re.search(r"- name: Tag must match version\.py\n(?:.*\n)*?        run: \|\n((?:          .*\n)+)", workflow)
    assert match
    return "\n".join(line[10:] for line in match.group(1).splitlines())


def test_tag_check_runs_first_on_tags_and_reads_the_tag_from_the_environment():
    workflow = read(".github/workflows/release.yml")
    build = job_block(workflow, "build")
    assert build.index("Tag must match version.py") < build.index("pytest") < build.index("build_exe.ps1")
    step = build[build.index("Tag must match version.py"):build.index("actions/setup-python")]
    assert "if: startsWith(github.ref, 'refs/tags/')" in step
    assert "TAG_NAME: ${{ github.ref_name }}" in step and "${{" not in extract_tag_check(workflow)  # betiğe doğrudan gömülmez


@pytest.mark.skipif(shutil.which("powershell") is None and shutil.which("pwsh") is None, reason="PowerShell yok")
@pytest.mark.parametrize("tag, ok", [(f"v{version.__version__}", True), ("v0.0.1", False), (version.__version__, False), ("", False)])
def test_tag_check_script_really_fails_on_a_version_mismatch(tmp_path, tag, ok):
    script = tmp_path / "tag_check.ps1"
    script.write_text(extract_tag_check(read(".github/workflows/release.yml")), encoding="utf-8")
    shell = shutil.which("pwsh") or shutil.which("powershell")
    env = {**os.environ, "TAG_NAME": tag}
    done = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(script)], cwd=ROOT, env=env, capture_output=True, timeout=120)
    assert (done.returncode == 0) is ok, done.stderr.decode("utf-8", "replace")


def test_build_tools_are_pinned():
    build, release = read("build_exe.ps1"), read(".github/workflows/release.yml")
    default = re.search(r'else \{ "(\d+\.\d+\.\d+)" \}', build)
    assert default and f'PYINSTALLER_VERSION: "{default.group(1)}"' in release  # betik ve iş akışı aynı sürümü kullanır
    assert 'pyinstaller==$pyInstallerVersion' in build and re.search(r'\$pyInstallerHooksVersion = "[\d.]+"', build)
    assert "--noupx" in build  # UPX ile sıkıştırma yok: kötü amaçlı yazılım tarayıcılarında yanlış alarmı azaltır
    installer = read("installer/build_installer.ps1")
    assert re.search(r'\$InnoVersion = "6\.\d+\.\d+"', installer) and "--version=$InnoVersion" in installer
    assert "choco install innosetup -y" not in installer  # sürümsüz kurulum kalmadı
