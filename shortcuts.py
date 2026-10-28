"""Genel kısayol kombinasyonlarının çözümlenmesi (Qt'den bağımsız).

Kombinasyonlar "Ctrl+Alt+F" biçimindedir: en az Ctrl, Alt ya da Win ve bir harf, rakam ya da F1-F12 tuşu gerekir.
"""

from __future__ import annotations

import re

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

_MODIFIERS = {"CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL, "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "META": MOD_WIN, "WIN": MOD_WIN}
_ORDER = (("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN))
_KEY = re.compile(r"^(?:[A-Z]|[0-9]|F(?:[1-9]|1[0-2]))$")


class HotkeyError(ValueError):
    """Kombinasyon geçersiz; `code`: "invalid" | "needs_modifier"."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_combo(text: str) -> tuple[int, int, str]:
    """"ctrl+alt+f" -> (değiştirici bayrakları, sanal tuş kodu, normal biçim "Ctrl+Alt+F")."""
    tokens = [t.strip() for t in str(text).split("+") if t.strip()]
    if len(tokens) < 2:
        raise HotkeyError("needs_modifier" if tokens else "invalid")
    *mod_tokens, key = tokens
    key = key.upper()
    if not _KEY.match(key):
        raise HotkeyError("invalid")
    mods = 0
    for token in mod_tokens:
        flag = _MODIFIERS.get(token.upper())
        if flag is None:
            raise HotkeyError("invalid")
        mods |= flag
    if not mods & (MOD_CONTROL | MOD_ALT | MOD_WIN):
        raise HotkeyError("needs_modifier")  # tek başına Shift ya da düz tuş yazı yazmayı bozar
    vk = 0x70 + int(key[1:]) - 1 if key.startswith("F") and len(key) > 1 else ord(key)
    normal = "+".join([name for name, flag in _ORDER if mods & flag] + [key])
    return mods, vk, normal


def normalise(text: str) -> str:
    return parse_combo(text)[2]
