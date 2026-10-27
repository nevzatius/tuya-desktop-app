"""Ortak test ayarları: mevcut testler Türkçe metinlere göre yazıldığı için her test Türkçe başlar."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def _turkish_ui():
    i18n.set_language("tr")
    i18n.set_currency(i18n.DEFAULT_CURRENCY)
    yield
    i18n.set_language("tr")
    i18n.set_currency(i18n.DEFAULT_CURRENCY)
