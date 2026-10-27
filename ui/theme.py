"""Koyu tema: renk paleti ve Qt stil sayfası (QSS)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0e1014"
SURFACE = "#161920"
SURFACE_2 = "#1d212a"
BORDER = "#242a36"
TEXT = "#e9ecf3"
MUTED = "#8b94a8"
OK = "#3ddc97"
WARN = "#ffb454"
DANGER = "#ff6b6b"

QSS = f"""
QWidget {{
    color: {TEXT};
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", sans-serif;
    font-size: 13px;
}}
QMainWindow, QWidget#root {{ background: {BG}; }}
QWidget#content {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 18px; font-weight: 600; }}
QLabel#stateBig {{ font-size: 28px; font-weight: 600; }}
QLabel#sub {{ color: {MUTED}; font-size: 13px; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#cardTitle {{ color: {MUTED}; font-size: 12px; font-weight: 600; letter-spacing: 1px; }}
QLabel#value {{ font-weight: 600; font-size: 14px; }}
QLabel#hex {{ color: {MUTED}; font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: 12px; }}

QLabel#pill {{
    padding: 5px 13px; border: 1px solid {BORDER}; border-radius: 14px;
    background: {SURFACE_2}; color: {MUTED}; font-size: 12px; font-weight: 600;
}}
QLabel#pill[tone="ok"]   {{ padding: 5px 13px; border: 1px solid rgba(61, 220, 151, 0.28); border-radius: 14px; background: rgba(61, 220, 151, 0.12); color: {OK}; }}
QLabel#pill[tone="warn"] {{ padding: 5px 13px; border: 1px solid rgba(255, 180, 84, 0.28); border-radius: 14px; background: rgba(255, 180, 84, 0.12); color: {WARN}; }}
QLabel#pill[tone="bad"]  {{ padding: 5px 13px; border: 1px solid rgba(255, 107, 107, 0.28); border-radius: 14px; background: rgba(255, 107, 107, 0.12); color: {DANGER}; }}

QLabel#banner {{
    background: rgba(255, 107, 107, 0.10); color: #ffb3b3;
    border: 1px solid rgba(255, 107, 107, 0.30); border-radius: 12px; padding: 10px 12px;
}}

QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 18px; }}
QFrame#segWrap {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}

QPushButton {{ outline: none; }}
QPushButton#seg {{
    background: transparent; border: none; border-radius: 10px;
    padding: 9px 0px; color: {MUTED}; font-weight: 600; font-size: 13px;
}}
QPushButton#seg:hover {{ color: {TEXT}; }}
QPushButton#seg:checked {{ background: #272d3a; color: {TEXT}; }}

QPushButton#chip {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 13px;
    padding: 11px 10px; text-align: left; font-weight: 600;
}}
QPushButton#chip:hover {{ background: {SURFACE_2}; border-color: #333b4b; }}
QPushButton#chip:pressed {{ background: #232835; }}

QPushButton#ghost {{
    background: transparent; border: 1px solid {BORDER}; border-radius: 10px;
    padding: 6px 12px; color: {MUTED}; font-size: 12px;
}}
QPushButton#ghost:hover {{ color: {TEXT}; background: {SURFACE_2}; }}
QPushButton#ghost:checked {{ color: {TEXT}; background: {SURFACE_2}; }}

QDialog {{ background: {BG}; }}
QLineEdit {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 10px;
    selection-background-color: #3b4a6b;
}}
QLineEdit:focus {{ border-color: #4c5d85; }}
QComboBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 7px 10px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {SURFACE_2}; }}
QDoubleSpinBox {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px 8px;
    selection-background-color: #3b4a6b;
}}
QDoubleSpinBox:focus {{ border-color: #4c5d85; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0px; border: none; }}
QCheckBox {{ color: {MUTED}; spacing: 6px; }}
QListWidget {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 6px; outline: none; }}
QListWidget::item {{ padding: 9px 8px; border-radius: 8px; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QListWidget::indicator, QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid #4a5368; background: {BG};
}}
QListWidget::indicator:checked, QCheckBox::indicator:checked {{ background: #8fb4ff; border-color: #8fb4ff; }}
QPushButton#primary {{
    background: #e8eefc; color: #10131a; border: none; border-radius: 12px;
    padding: 11px 16px; font-weight: 600; font-size: 13px;
}}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#primary:disabled {{ background: #3a4152; color: #8b94a8; }}
QPushButton#deviceBtn {{
    background: transparent; border: none; color: {TEXT}; font-size: 18px; font-weight: 600;
    padding: 2px 6px; text-align: left; border-radius: 8px;
}}
QPushButton#deviceBtn:hover {{ background: {SURFACE_2}; }}
QPushButton#deviceBtn::menu-indicator {{ image: none; width: 0px; }}

QPushButton#iconBtn {{
    background: transparent; border: none; color: {MUTED}; font-size: 16px;
    padding: 2px 6px; border-radius: 8px;
}}
QPushButton#iconBtn:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#iconBtn::menu-indicator {{ image: none; width: 0px; }}

QPlainTextEdit#log {{
    background: #0a0c10; border: 1px solid {BORDER}; border-radius: 12px; padding: 8px;
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace; font-size: 11px; color: #9aa3b8;
}}

QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2a303d; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #3a4254; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px; }}
QMenu {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SURFACE_2}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor("#8fb4ff"))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#b6a4ff"))
    app.setPalette(palette)
    app.setStyleSheet(QSS)
    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 9.5))
    app.setFont(font)
