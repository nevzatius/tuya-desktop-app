"""Ana ekrandaki hazır ayar çipleri ve kullanıcı ayarlarını kaydetme/düzenleme/silme/gizleme pencereleri."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import i18n
from i18n import tr
from version import APP_NAME

from .presets import MAX_NAME, MAX_USER_PRESETS, Preset, PresetError, PresetStore
from .scene_editor import SceneEditor

COLUMNS = 3
MAX_VISIBLE_ROWS = 4  # bundan fazlası çip alanında kaydırılır


def dot_icon(rgb: tuple[int, int, int], size: int = 16) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(*rgb))
    p.drawEllipse(3, 3, size * 2 - 6, size * 2 - 6)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def error_text(error: PresetError) -> str:
    return tr(f"presets.error_{error.code}", max=MAX_NAME if error.code == "too_long" else MAX_USER_PRESETS)


class PresetDialog(QDialog):
    """Hazır ayar ekle (varsayılan değerler şu anki durum) ya da düzenle. Kaydetmeyi kendisi yapar."""

    def __init__(self, store: PresetStore, editing: Preset | None, values: dict | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store, self.editing = store, editing
        self.result_preset: Preset | None = None
        self.setWindowTitle(tr("presets.dialog_edit") if editing else tr("presets.dialog_new"))
        self.setMinimumWidth(380)
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        label = QLabel(tr("presets.name_label"))
        label.setObjectName("muted")
        box.addWidget(label)
        self.name_edit = QLineEdit(editing.name if editing else "")
        self.name_edit.setPlaceholderText(tr("presets.name_placeholder"))
        self.name_edit.setMaxLength(MAX_NAME + 8)  # fazlasını doğrulama anlaşılır bir hata ile reddeder
        box.addWidget(self.name_edit)
        self.error = QLabel()
        self.error.setObjectName("banner")
        self.error.setWordWrap(True)
        self.error.hide()
        box.addWidget(self.error)
        self.editor = SceneEditor("scene")
        start = values or {}
        if editing is not None:
            start = {"mode": editing.mode, "bright": editing.bright, "temp": editing.temp, "hue": editing.hue, "sat": editing.sat}
        self.editor.set_values(**start)
        box.addWidget(self.editor)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("controller.cancel"))
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton(tr("presets.save"))
        self.save_button.setObjectName("primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)
        box.addLayout(buttons)

    def accept(self) -> None:  # noqa: D102 - Qt geçersiz kılma
        v = self.editor.values()
        try:
            if self.editing is None:
                preset = self.store.add(self.name_edit.text(), v["mode"], v["bright"], v["temp"], v["hue"], v["sat"])
            else:
                preset = self.store.update(self.editing.key, self.name_edit.text(), v["mode"], v["bright"], v["temp"], v["hue"], v["sat"])
        except PresetError as exc:
            self.error.setText(error_text(exc))
            self.error.show()
            return
        except OSError as exc:  # disk dolu / izin yok
            self.error.setText(tr("presets.error_write", error=exc))
            self.error.show()
            return
        self.result_preset = preset
        super().accept()


class ManagePresetsDialog(QDialog):
    """Tüm hazır ayarların listesi: düzenle, sil (kullanıcı ayarları), gizle/göster (yerleşik ayarlar)."""

    def __init__(self, section: PresetsSection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.section = section
        self.setWindowTitle(tr("presets.manage_title"))
        self.setMinimumSize(380, 420)
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(lambda *_: self._sync_buttons())
        self.list.itemDoubleClicked.connect(lambda *_: self._edit())
        box.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.edit_button = QPushButton(tr("presets.edit"))
        self.delete_button = QPushButton(tr("presets.delete"))
        self.hide_button = QPushButton(tr("presets.hide"))
        for button, slot in ((self.edit_button, self._edit), (self.delete_button, self._delete), (self.hide_button, self._toggle)):
            button.setObjectName("ghost")
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch()
        close = QPushButton(tr("presets.close"))
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        box.addLayout(row)
        self.refresh()

    def selected_key(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh(self, keep: str | None = None) -> None:
        keep = keep or self.selected_key()
        self.list.clear()
        store = self.section.store
        for preset in store.all():
            tags = []
            if preset.builtin:
                tags.append(tr("presets.builtin_tag"))
            if store.is_hidden(preset.key):
                tags.append(tr("presets.hidden_tag"))
            text = f"{preset.name}   ·   {', '.join(tags)}" if tags else preset.name
            item = QListWidgetItem(dot_icon(preset.swatch()), text)
            item.setData(Qt.ItemDataRole.UserRole, preset.key)
            self.list.addItem(item)
            if preset.key == keep:
                self.list.setCurrentItem(item)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        key = self.selected_key()
        preset = self.section.store.get(key) if key else None
        self.edit_button.setEnabled(preset is not None and not preset.builtin)
        self.delete_button.setEnabled(preset is not None and not preset.builtin)
        self.hide_button.setEnabled(preset is not None and preset.builtin)
        hidden = preset is not None and self.section.store.is_hidden(preset.key)
        self.hide_button.setText(tr("presets.show") if hidden else tr("presets.hide"))

    def _edit(self) -> None:
        key = self.selected_key()
        if key and self.section.edit(key):
            self.refresh(key)

    def _delete(self) -> None:
        key = self.selected_key()
        if key and self.section.delete(key):
            self.refresh()

    def _toggle(self) -> None:
        key = self.selected_key()
        if key:
            self.section.toggle_hidden(key)
            self.refresh(key)


class PresetsSection(QWidget):
    """"Hazır ayarlar" bölümü: başlık, çipler (çoksa kaydırılır), "Şu anki durumu kaydet" ve "Yönet"."""

    applyRequested = Signal(object)  # Preset
    changed = Signal()  # kullanıcı ayarları ya da gizlenenler değişti

    def __init__(
        self,
        store: PresetStore,
        current_scene: Callable[[], dict],
        confirm: Callable[[QWidget, str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self._current_scene = current_scene
        self._confirm = confirm or self._default_confirm
        self.buttons: list[QPushButton] = []
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        title = QLabel(i18n.upper(tr("main.presets")))
        title.setObjectName("cardTitle")
        box.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._holder = QWidget()
        self._holder.setObjectName("content")
        self._grid = QGridLayout(self._holder)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        self.scroll.setWidget(self._holder)
        box.addWidget(self.scroll)

        tools = QHBoxLayout()
        self.save_button = QPushButton(tr("presets.save_current"))
        self.save_button.setObjectName("ghost")
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_current)
        self.manage_button = QPushButton(tr("presets.manage"))
        self.manage_button.setObjectName("ghost")
        self.manage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.manage_button.clicked.connect(self.manage)
        tools.addWidget(self.save_button)
        tools.addStretch()
        tools.addWidget(self.manage_button)
        box.addLayout(tools)
        self.refresh()

    @staticmethod
    def _default_confirm(parent: QWidget, text: str) -> bool:
        box = QMessageBox(QMessageBox.Icon.Question, APP_NAME, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
        box.button(QMessageBox.StandardButton.Yes).setText(tr("presets.delete"))
        box.button(QMessageBox.StandardButton.No).setText(tr("controller.cancel"))
        return box.exec() == QMessageBox.StandardButton.Yes

    # -- çipler -----------------------------------------------------------------

    def refresh(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()  # deleteLater olay döngüsüne dönene kadar bekler; o sırada eski çip çizilmesin
                widget.setParent(None)
                widget.deleteLater()
        self.buttons = []
        presets = self.store.visible()
        for index, preset in enumerate(presets):
            button = QPushButton(preset.name)
            button.setObjectName("chip")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIcon(dot_icon(preset.swatch()))
            button.setToolTip(preset.name)
            button.setProperty("preset", preset.name)
            button.setProperty("presetKey", preset.key)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)  # uzun ad sütunu genişletmesin
            button.setFixedHeight(button.sizeHint().height())
            button.clicked.connect(lambda _checked=False, p=preset: self.applyRequested.emit(p))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(lambda pos, b=button, p=preset: self._chip_menu(b, p, pos))
            self._grid.addWidget(button, index // COLUMNS, index % COLUMNS)
            self.buttons.append(button)
        for column in range(COLUMNS):
            self._grid.setColumnStretch(column, 1)
        rows = max(1, -(-len(presets) // COLUMNS))
        row_height = self.buttons[0].sizeHint().height() if self.buttons else 44
        spacing = self._grid.verticalSpacing()
        self.scroll.setFixedHeight(min(rows, MAX_VISIBLE_ROWS) * row_height + (min(rows, MAX_VISIBLE_ROWS) - 1) * spacing + 2)

    def chip_menu(self, preset: Preset) -> QMenu:
        menu = QMenu(self)
        if preset.builtin:
            menu.addAction(tr("presets.hide"), lambda: self.toggle_hidden(preset.key))
        else:
            menu.addAction(tr("presets.edit"), lambda: self.edit(preset.key))
            menu.addAction(tr("presets.delete"), lambda: self.delete(preset.key))
        return menu

    def _chip_menu(self, button: QPushButton, preset: Preset, pos) -> None:
        self.chip_menu(preset).exec(button.mapToGlobal(pos))

    # -- işlemler -----------------------------------------------------------------

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self.window(), APP_NAME, text)

    def save_current(self) -> bool:
        dialog = PresetDialog(self.store, None, self._current_scene(), self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.refresh()
        self.changed.emit()
        return True

    def edit(self, key: str) -> bool:
        preset = self.store.get(key)
        if preset is None or preset.builtin:
            return False
        dialog = PresetDialog(self.store, preset, None, self.window())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.refresh()
        self.changed.emit()
        return True

    def delete(self, key: str) -> bool:
        preset = self.store.get(key)
        if preset is None or preset.builtin:
            return False
        if not self._confirm(self.window(), tr("presets.delete_confirm", name=preset.name)):
            return False
        try:
            self.store.delete(key)
        except PresetError as exc:
            self._warn(error_text(exc))
            return False
        except OSError as exc:
            self._warn(tr("presets.error_write", error=exc))
            return False
        self.refresh()
        self.changed.emit()
        return True

    def toggle_hidden(self, key: str) -> bool:
        try:
            self.store.set_hidden(key, not self.store.is_hidden(key))
        except PresetError as exc:
            self._warn(error_text(exc))
            return False
        except OSError as exc:
            self._warn(tr("presets.error_write", error=exc))
            return False
        self.refresh()
        self.changed.emit()
        return True

    def manage(self) -> None:
        ManagePresetsDialog(self, self.window()).exec()
