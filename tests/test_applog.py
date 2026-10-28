"""Döner günlük dosyası (app.log): her şey maskelenir, 3 dosyayla sınırlıdır, tanılama raporuna girer."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import applog  # noqa: E402
import diagnostics as diag  # noqa: E402
import light_core as lc  # noqa: E402
from privacy import MASK  # noqa: E402

SECRETS = {
    "local_key": "FAKEKEY#9876543210ab",
    "device_id": "bfFAKEDEVICEID0000001",
    "uuid": "fakeuuid0123456789",
    "name": "Ayşe yatak odası",
}
PATTERNS = {
    "mac": "AA:BB:CC:DD:EE:FF",
    "mac_dash": "11-22-33-44-55-66",
    "guid": "0f8fad5b-d9cb-469f-a165-70867728950e",
    "hex": "deadbeefcafebabe0123456789abcdef",
}
ALL = {**SECRETS, **PATTERNS}


class Logging:
    """Kök günlükçünün durumunu geri yükleyen bağlam: testler birbirini etkilemesin."""

    def __init__(self, path: Path, **kwargs):
        self.path, self.kwargs = path, kwargs

    def __enter__(self):
        self.level = logging.getLogger().level
        self.handler = applog.setup(self.path, **self.kwargs)
        return self.handler

    def __exit__(self, *exc):
        applog.shutdown()
        logging.getLogger().setLevel(self.level)


@pytest.fixture()
def log_file(tmp_path):
    path = tmp_path / "app.log"
    with Logging(path, secrets=lambda: SECRETS.values()) as handler:
        assert handler is not None
        yield path


def text_of(path: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(path.parent.glob("app.log*")))


def test_nothing_secret_reaches_the_file_in_any_form(log_file):
    log = logging.getLogger("tuya_light.test")
    for key, value in ALL.items():
        log.info("plain %s", value)
        log.warning(f"fstring {value}")
        log.error("with args %s and %r", value, {"k": value})
    log.info("lowercase %s / compact %s", PATTERNS["mac"].lower(), SECRETS["local_key"].lower())
    try:
        raise RuntimeError(f"boom {SECRETS['local_key']} {PATTERNS['mac']}")
    except RuntimeError:
        log.exception("failed for %s", SECRETS["device_id"])  # hata izi de maskelenir
    text = text_of(log_file)
    for key, value in ALL.items():
        assert value not in text, key
    assert text.count(MASK) >= len(ALL) * 3
    assert "RuntimeError" in text and "failed for" in text  # günlük işe yarar kalır: yalnızca değerler gider


def test_unknown_values_are_masked_by_pattern_even_without_a_secrets_provider(tmp_path):
    with Logging(tmp_path / "app.log"):
        logging.getLogger("tuya_light.test").info("found %s guid %s hex %s", PATTERNS["mac"], PATTERNS["guid"], PATTERNS["hex"])
    text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert not any(v in text for v in PATTERNS.values()) and MASK in text


def test_a_failing_secrets_provider_does_not_drop_or_leak_the_line(tmp_path):
    def broken():
        raise RuntimeError("provider down")

    with Logging(tmp_path / "app.log", secrets=broken):
        logging.getLogger("tuya_light.test").info("mac %s", PATTERNS["mac"])
    text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "mac " in text and PATTERNS["mac"] not in text


def test_secrets_added_later_are_masked_too(tmp_path):
    known: list[str] = []
    with Logging(tmp_path / "app.log", secrets=lambda: known):
        known.append("LateAddedKey#123456")  # kurulum sihirbazı sonradan ışık ekleyebilir
        logging.getLogger("tuya_light.test").info("key LateAddedKey#123456")
    assert "LateAddedKey" not in (tmp_path / "app.log").read_text(encoding="utf-8")


def test_uncaught_exceptions_are_logged_masked(log_file, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: seen.append(a))  # özgün kanca
    monkeypatch.setattr("threading.excepthook", lambda a: seen.append(a))
    applog.install_excepthooks()
    try:
        raise ValueError(f"bad {SECRETS['local_key']}")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    text = text_of(log_file)
    assert "uncaught exception" in text and "ValueError" in text and SECRETS["local_key"] not in text
    assert len(seen) == 1  # özgün kanca da çalıştı


def test_rotation_limits_are_about_one_megabyte_times_three():
    assert applog.MAX_BYTES == 1_000_000 and applog.BACKUPS == 2


def test_rotation_keeps_at_most_three_files_and_masks_across_them(tmp_path):
    with Logging(tmp_path / "app.log", secrets=lambda: [SECRETS["local_key"]], max_bytes=2_000, backups=2):
        log = logging.getLogger("tuya_light.test")
        for i in range(200):
            log.info("line %03d key %s mac %s", i, SECRETS["local_key"], PATTERNS["mac"])
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["app.log", "app.log.1", "app.log.2"]
    assert all(p.stat().st_size <= 2_000 + 200 for p in tmp_path.iterdir())
    text = text_of(tmp_path / "app.log")
    assert SECRETS["local_key"] not in text and PATTERNS["mac"] not in text
    assert "line 199" in text and "line 000" not in text  # en eski satırlar düştü


def test_setup_twice_keeps_a_single_handler(tmp_path):
    root = logging.getLogger()
    with Logging(tmp_path / "a.log"):
        applog.setup(tmp_path / "b.log")
        assert len([h for h in root.handlers if getattr(h, "_tuya_applog", False)]) == 1
    assert not [h for h in root.handlers if getattr(h, "_tuya_applog", False)]


def test_unwritable_location_does_not_break_the_app(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert applog.setup(blocker / "sub" / "app.log") is None  # klasör oluşturulamaz


def test_default_path_is_in_the_user_data_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert applog.log_path().name == "app.log" and applog.log_path().parent.parent == tmp_path


# -- tail -----------------------------------------------------------------------------------------------------------


def test_tail_returns_last_lines_oldest_first_and_spans_the_rotated_file(tmp_path):
    path = tmp_path / "app.log"
    (tmp_path / "app.log.1").write_text("".join(f"old {i}\n" for i in range(10)), encoding="utf-8")
    path.write_text("".join(f"new {i}\n" for i in range(3)), encoding="utf-8")
    assert applog.tail(5, path) == ["old 8", "old 9", "new 0", "new 1", "new 2"]
    assert applog.tail(2, path) == ["new 1", "new 2"]


def test_tail_of_missing_file_is_empty(tmp_path):
    assert applog.tail(10, tmp_path / "nope.log") == []


def test_tail_masks_again_when_reading(tmp_path):
    """Dosyaya başka yoldan (eski sürüm, elle) sızmış bir değer bile rapora girmez."""
    path = tmp_path / "app.log"
    path.write_text(f"raw {SECRETS['local_key']} {PATTERNS['mac']} {PATTERNS['hex']}\n", encoding="utf-8")
    lines = applog.tail(10, path, secrets=SECRETS.values())
    assert lines and not any(v in lines[0] for v in (SECRETS["local_key"], PATTERNS["mac"], PATTERNS["hex"]))


def test_tail_reads_only_the_end_of_a_big_file(tmp_path):
    path = tmp_path / "app.log"
    path.write_text("".join(f"line {i:06d}\n" for i in range(40_000)), encoding="utf-8")  # ~480 KB
    assert applog.tail(3, path) == ["line 039997", "line 039998", "line 039999"]


# -- tanılama raporu ----------------------------------------------------------------------------------------------


def fake_light() -> lc.Config:
    return lc.Config(device_id=SECRETS["device_id"], local_key=SECRETS["local_key"], uuid=SECRETS["uuid"], name=SECRETS["name"], address=PATTERNS["mac"])


def test_report_includes_the_last_log_lines_without_secrets(log_file):
    light = fake_light()
    log = logging.getLogger("tuya_light.test")
    for i in range(80):
        log.info("event %02d for %s at %s", i, light.device_id, light.address)
    log.warning("a custom note")
    report = diag.build_report([light], file_log=applog.tail(path=log_file, secrets=diag.known_secrets([light])))
    assert "### Log file" in report and "a custom note" in report and "event 79" in report
    assert "event 00" not in report  # yalnızca son satırlar (TAIL_LINES)
    for value in (*SECRETS.values(), *PATTERNS.values()):
        assert value not in report


def test_report_without_a_log_file_says_empty():
    report = diag.build_report([])
    assert "### Log file" in report and "(empty)" in report
