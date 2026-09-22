"""Image joining/stitching tool: combine several images side by side."""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..constants import IMAGE_EXTENSIONS
from ..core.convert import pil_to_qpixmap
from ..core.image_ops import load_with_orientation
from ..core.stitch_ops import StitchOptions, compose

H_ALIGN_LABELS = {"Top": "top", "Center": "center", "Bottom": "bottom"}
V_ALIGN_LABELS = {"Left": "left", "Center": "center", "Right": "right"}
RESIZE_LABELS = {
    "No resize (keep original sizes)": "none",
    "Match smallest image": "match_smallest",
    "Match largest image": "match_largest",
    "Custom size": "custom",
}

THUMB = 64
PREVIEW_CAP = 360


class StitchDialog(QDialog):
    def __init__(self, parent=None, initial_paths: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Join Images")
        self.resize(1000, 640)

        self._image_cache: dict[str, Image.Image] = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._update_preview)

        self._bg_color = QColor(255, 255, 255)

        self._build_ui()
        if initial_paths:
            self.add_paths(initial_paths)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Images...")
        btn_remove = QPushButton("Remove Selected")
        btn_up = QPushButton("Move Up")
        btn_down = QPushButton("Move Down")
        for b in (btn_add, btn_remove, btn_up, btn_down):
            btn_row.addWidget(b)
        left.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(THUMB, THUMB))
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.model().rowsMoved.connect(self._queue_preview)
        left.addWidget(self.list_widget, stretch=1)

        root.addLayout(left, stretch=1)

        # -- middle: preview ---------------------------------------------------
        middle = QVBoxLayout()
        middle.addWidget(QLabel("Preview"))
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(360, 360)
        self.preview_label.setStyleSheet("background-color: #3a3a3d; border: 1px solid #555;")
        middle.addWidget(self.preview_label, stretch=1)
        root.addLayout(middle, stretch=2)

        # -- right: options ------------------------------------------------------
        right = QVBoxLayout()
        options_box = QGroupBox("Layout")
        form = QFormLayout(options_box)

        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Horizontal", "Vertical", "Grid"])
        form.addRow("Direction:", self.direction_combo)

        self.columns_spin = QSpinBox()
        self.columns_spin.setRange(1, 50)
        self.columns_spin.setValue(3)
        form.addRow("Grid columns:", self.columns_spin)

        self.spacing_spin = QSpinBox()
        self.spacing_spin.setRange(0, 500)
        self.spacing_spin.setValue(10)
        form.addRow("Spacing (px):", self.spacing_spin)

        self.align_combo = QComboBox()
        form.addRow("Alignment:", self.align_combo)

        self.resize_combo = QComboBox()
        self.resize_combo.addItems(RESIZE_LABELS.keys())
        form.addRow("Size:", self.resize_combo)

        self.custom_size_spin = QSpinBox()
        self.custom_size_spin.setRange(8, 10000)
        self.custom_size_spin.setValue(512)
        form.addRow("Custom (px):", self.custom_size_spin)

        bg_row = QHBoxLayout()
        self.bg_button = QPushButton()
        self.bg_button.setFixedSize(28, 22)
        self.transparent_check = QCheckBox("Transparent")
        bg_row.addWidget(self.bg_button)
        bg_row.addWidget(self.transparent_check)
        form.addRow("Background:", bg_row)

        right.addWidget(options_box)
        right.addStretch(1)

        save_row = QHBoxLayout()
        self.btn_save = QPushButton("Save As...")
        self.btn_close = QPushButton("Close")
        save_row.addWidget(self.btn_save)
        save_row.addWidget(self.btn_close)
        right.addLayout(save_row)

        right_container = QWidget()
        right_container.setLayout(right)
        right_container.setMinimumWidth(280)
        root.addWidget(right_container, stretch=1)

        self._update_bg_swatch()
        self._update_align_choices()

        btn_add.clicked.connect(self._add_files_dialog)
        btn_remove.clicked.connect(self._remove_selected)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)
        self.bg_button.clicked.connect(self._pick_color)
        self.transparent_check.toggled.connect(self._on_transparent_toggled)
        self.direction_combo.currentIndexChanged.connect(self._on_direction_changed)
        self.btn_save.clicked.connect(self._save_as)
        self.btn_close.clicked.connect(self.close)

        for widget in (self.direction_combo, self.columns_spin, self.spacing_spin, self.align_combo,
                       self.resize_combo, self.custom_size_spin):
            if isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._queue_preview)
            else:
                widget.currentIndexChanged.connect(self._queue_preview)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------
    def add_paths(self, paths: list[str]) -> None:
        for path in paths:
            if Path(path).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            try:
                image = load_with_orientation(path)
            except Exception:
                continue
            self._image_cache[path] = image
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            thumb = image.copy()
            thumb.thumbnail((THUMB, THUMB), Image.Resampling.LANCZOS)
            item.setIcon(QIcon(pil_to_qpixmap(thumb)))
            self.list_widget.addItem(item)
        self._queue_preview()

    def _add_files_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Images", "", f"Images ({exts})")
        if paths:
            self.add_paths(paths)

    def _remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._queue_preview()

    def _move_up(self) -> None:
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
            self._queue_preview()

    def _move_down(self) -> None:
        row = self.list_widget.currentRow()
        if 0 <= row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            self._queue_preview()

    def _ordered_paths(self) -> list[str]:
        return [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
    def _update_align_choices(self) -> None:
        self.align_combo.blockSignals(True)
        self.align_combo.clear()
        if self.direction_combo.currentText() == "Vertical":
            self.align_combo.addItems(V_ALIGN_LABELS.keys())
        else:
            self.align_combo.addItems(H_ALIGN_LABELS.keys())
        self.align_combo.blockSignals(False)

    def _on_direction_changed(self) -> None:
        self._update_align_choices()
        self.columns_spin.setEnabled(self.direction_combo.currentText() == "Grid")
        self._queue_preview()

    def _update_bg_swatch(self) -> None:
        if self.transparent_check.isChecked():
            self.bg_button.setStyleSheet("background: repeating-linear-gradient(45deg, #999, #999 4px, #ccc 4px, #ccc 8px); border: 1px solid #555;")
        else:
            self.bg_button.setStyleSheet(f"background-color: {self._bg_color.name()}; border: 1px solid #555;")

    def _pick_color(self) -> None:
        color = QColorDialogCompat.get_color(self, self._bg_color)
        if color is not None:
            self._bg_color = color
            self._update_bg_swatch()
            self._queue_preview()

    def _on_transparent_toggled(self, _checked: bool) -> None:
        self._update_bg_swatch()
        self._queue_preview()

    def _current_options(self) -> StitchOptions:
        direction_map = {"Horizontal": "horizontal", "Vertical": "vertical", "Grid": "grid"}
        direction = direction_map[self.direction_combo.currentText()]
        align_labels = V_ALIGN_LABELS if direction == "vertical" else H_ALIGN_LABELS
        align = align_labels.get(self.align_combo.currentText(), "center")
        if self.transparent_check.isChecked():
            bg = (0, 0, 0, 0)
        else:
            bg = (self._bg_color.red(), self._bg_color.green(), self._bg_color.blue(), 255)
        return StitchOptions(
            direction=direction,
            spacing=self.spacing_spin.value(),
            background=bg,
            align=align,
            columns=self.columns_spin.value(),
            resize_mode=RESIZE_LABELS[self.resize_combo.currentText()],
            custom_size=self.custom_size_spin.value(),
        )

    # ------------------------------------------------------------------
    # Preview / save
    # ------------------------------------------------------------------
    def _queue_preview(self, *_args) -> None:
        self._preview_timer.start()

    def _update_preview(self) -> None:
        paths = self._ordered_paths()
        if not paths:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Add images to preview the result")
            return
        images = [self._capped(self._image_cache[p]) for p in paths if p in self._image_cache]
        if not images:
            return
        try:
            result = compose(images, self._current_options())
        except Exception as exc:  # noqa: BLE001
            self.preview_label.setText(f"Preview error: {exc}")
            return
        pixmap = pil_to_qpixmap(result)
        scaled = pixmap.scaled(
            self.preview_label.width() - 10, self.preview_label.height() - 10,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    @staticmethod
    def _capped(image: Image.Image, max_dim: int = PREVIEW_CAP) -> Image.Image:
        if max(image.size) <= max_dim:
            return image
        capped = image.copy()
        capped.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        return capped

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._queue_preview()

    def _save_as(self) -> None:
        paths = self._ordered_paths()
        if not paths:
            QMessageBox.information(self, "Join Images", "Add at least one image first.")
            return
        images = [self._image_cache[p] for p in paths if p in self._image_cache]
        options = self._current_options()
        try:
            result = compose(images, options)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Join Images", f"Could not compose the image:\n{exc}")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Joined Image", "joined.png",
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp);;TIFF (*.tiff);;WEBP (*.webp)",
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            if ext in (".jpg", ".jpeg"):
                result = result.convert("RGB")
                result.save(path, quality=95, optimize=True)
            else:
                result.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Join Images", f"Could not save the image:\n{exc}")
            return
        QMessageBox.information(self, "Join Images", f"Saved {path}")


class QColorDialogCompat:
    """Thin wrapper so QColorDialog is imported lazily (keeps import list tidy)."""

    @staticmethod
    def get_color(parent, initial: QColor) -> QColor | None:
        from PyQt6.QtWidgets import QColorDialog

        color = QColorDialog.getColor(initial, parent, "Choose Background Color")
        return color if color.isValid() else None
