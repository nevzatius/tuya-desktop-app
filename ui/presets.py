"""Tek dokunuşla uygulanan hazır ışık ayarları."""

from __future__ import annotations

from dataclasses import dataclass

from .colors import RGB, hs_rgb, white_rgb


@dataclass(frozen=True)
class Preset:
    name: str
    mode: str  # "white" | "colour"
    bright: int  # yüzde 1-100
    temp: int = 0  # beyaz mod: 0 sıcak … 100 soğuk
    hue: int = 0  # renk modu: 0-360
    sat: int = 0  # renk modu: 0-1000

    def swatch(self) -> RGB:
        if self.mode == "white":
            return white_rgb(self.temp)
        return hs_rgb(self.hue, self.sat)


PRESETS: tuple[Preset, ...] = (
    Preset("Okuma", "white", 85, temp=45),
    Preset("Odak", "white", 100, temp=100),
    Preset("Gece", "white", 8, temp=0),
    Preset("Film", "colour", 20, hue=28, sat=900),
    Preset("Romantik", "colour", 25, hue=338, sat=850),
    Preset("Okyanus", "colour", 45, hue=200, sat=900),
)
