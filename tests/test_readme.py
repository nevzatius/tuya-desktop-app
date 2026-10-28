"""README.md / README.tr.md: bağlantılar, görseller, bölüm bağlantıları (anchor), komutlar ve dürüst durum tablosu."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = ["README.md", "README.tr.md"]
REPO_URL = "https://github.com/nevzatius/tuya-desktop-app"


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def slug(heading: str) -> str:
    """GitHub'ın başlık -> anchor kuralı (yeterince yakın)."""
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return re.sub(r"\s", "-", text)


def headings(text: str) -> set[str]:
    in_code, found = False, set()
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code and re.match(r"#{1,6} ", line):
            found.add(slug(re.sub(r"^#+\s*", "", line)))
    return found


def links(text: str) -> list[str]:
    return re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'src="([^"]+)"', text)


@pytest.mark.parametrize("name", READMES)
def test_relative_links_images_and_anchors_resolve(name):
    text = read(name)
    anchors = headings(text)
    for target in links(text):
        if target.startswith(("http://", "https://")):
            continue
        if target.startswith("#"):
            assert target[1:] in anchors, f"{name}: broken anchor {target}"
        else:
            assert (ROOT / target.split("#")[0]).exists(), f"{name}: missing file {target}"


@pytest.mark.parametrize("name", READMES)
def test_github_links_point_at_the_renamed_repo(name):
    text = read(name)
    for target in links(text):
        if "github.com/nevzatius" in target:
            assert target.startswith(REPO_URL), target
    # Eski veri klasörü adı (OdamdakiIsik) taşıma notunda bilerek geçer; eski uygulama adı ve eski depo adı geçmemeli.
    assert "Odamdaki Işık" not in text and "odamdaki-isik" not in text.lower() and "tuya-desktop_app" not in text


@pytest.mark.parametrize("name", READMES)
def test_scripts_and_files_mentioned_in_code_exist(name):
    text = read(name)
    code = "\n".join(re.findall(r"```[^\n]*\n(.*?)```", text, re.S))
    for path in set(re.findall(r"(?:\.\\|\b)([\w./\\-]+\.(?:ps1|bat|py|txt))\b", code)):
        assert (ROOT / path.replace("\\", "/")).exists(), f"{name}: {path} does not exist"


def test_readmes_link_to_each_other_at_the_top():
    assert "[Türkçe](README.tr.md)" in read("README.md").split("\n\n")[1]
    assert "[English](README.md)" in read("README.tr.md").split("\n\n")[1]


@pytest.mark.parametrize(("name", "quick", "after"), [("README.md", "## Quick start", "## Features"), ("README.tr.md", "## Hızlı başlangıç", "## Özellikler")])
def test_quick_start_is_three_steps_with_smartscreen_and_key_box(name, quick, after):
    section = read(name).split(quick, 1)[1].split(after, 1)[0]
    steps = re.findall(r"(?m)^(\d+)\. ", section)
    assert steps == ["1", "2", "3"]
    assert "SmartScreen" in section and ("More info → Run anyway" in section or "Yine de çalıştır" in section)
    assert "code-signed" in section or "kod imzalı" in section
    box = section.split("###", 1)[1].split("\n\n")[0]  # "Why does the app need a key?" kutusu hemen altında
    assert "local key" in box.lower() or "yerel anahtar" in box.lower()


@pytest.mark.parametrize("name", READMES)
def test_unverified_features_have_their_own_status_rows(name):
    text = read(name)
    table = text.split("## Status" if name == "README.md" else "## Durum", 1)[1].split("\n## ", 1)[0]
    rows = [r for r in table.splitlines() if r.startswith("|")]
    blink = [r for r in rows if "Blink" in r or "Yanıp söndür" in r]
    trouble = [r for r in rows if "Troubleshooter" in r or "Sorun giderici" in r]
    assert len(blink) == 1 and len(trouble) == 1 and blink != trouble
    for row in (*blink, *trouble):
        assert "not yet verified" in row or "doğrulanmadı" in row


def test_both_readmes_show_the_same_screenshots_in_their_own_language():
    en, tr = read("README.md"), read("README.tr.md")
    shots_en = re.findall(r"docs/screenshots/en/([\w-]+\.png)", en)
    shots_tr = re.findall(r"docs/screenshots/tr/([\w-]+\.png)", tr)
    assert sorted(shots_en) == sorted(shots_tr) and len(shots_en) >= 4
    srcs = lambda text: re.findall(r'src="([^"]+)"', text)  # noqa: E731  (geliştirme bölümündeki yorum sayılmaz)
    assert all("screenshots/en/" in src for src in srcs(en)) and all("screenshots/tr/" in src for src in srcs(tr))


def test_cli_is_documented_as_turkish_only_and_contributing_exists():
    assert "Turkish-only" in read("README.md") and "yalnızca Türkçedir" in read("README.tr.md")
    assert "locales/en.py" in read("CONTRIBUTING.md") and "python -m pytest tests" in read("CONTRIBUTING.md")
