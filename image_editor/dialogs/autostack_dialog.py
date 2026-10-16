"""Auto-Stack dialog: combine many overlapping photos into one image by
matching visual patterns between them - unlike Join Images, which just lays
photos out on a fixed grid without looking at their content."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..constants import IMAGE_EXTENSIONS
from ..core import image_ops
from ..core.autostack_ops import MODE_FLAT, MODE_PANORAMA, AutoStackOptions
from ..core.convert import pil_to_qimage, pil_to_qpixmap
from ..workers.autostack_worker import AutoStackWorker

THUMB = 64

MODE_LABELS = {
    "Overhead / flat scene (garden, field, document)": MODE_FLAT,
    "Rotating camera (classic panorama)": MODE_PANORAMA,
}

WORKING_SIZE_LABELS = {
    "1500 px (fastest)": 1500,
    "2000 px (recommended)": 2000,
    "3000 px": 3000,
    "Full resolution (slow, high memory)": 0,
}


class _ThumbSignals(QObject):
    ready = pyqtSignal(str, QImage)
    failed = pyqtSignal(str)


class _ThumbWorker(QRunnable):
    """Decodes a small list-preview thumbnail off the GUI thread.

    Unlike Join Images, Auto-Stack never keeps full-resolution decodes
    around in the dialog itself - AutoStackWorker re-reads each file right
    before stitching - so this only ever needs a cheap small thumbnail.
    """

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _ThumbSignals()

    def run(self) -> None:
        try:
            thumb = image_ops.load_thumbnail(self.path, THUMB)
            qimage = pil_to_qimage(thumb)
        except Exception:
            try:
                self.signals.failed.emit(self.path)
            except RuntimeError:
                pass
            return
        try:
            self.signals.ready.emit(self.path, qimage)
        except RuntimeError:
            # Dialog was closed while this decode was still in flight.
            pass


class AutoStackDialog(QDialog):
    def __init__(self, parent=None, initial_paths: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Stack (Smart Stitch)")
        self.resize(1000, 640)

        self._pool = QThreadPool.globalInstance()
        self._worker: AutoStackWorker | None = None
        self._result = None  # PIL.Image.Image | None

        self._build_ui()
        if initial_paths:
            self.add_paths(initial_paths)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        hint = QLabel(
            "Add overlapping photos of the same scene (e.g. a garden shot from "
            "many positions above). Auto-Stack matches visual patterns between "
            "them and blends everything into one combined image."
        )
        hint.setWordWrap(True)
        left.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add Images...")
        btn_add_folder = QPushButton("Add Folder...")
        btn_remove = QPushButton("Remove Selected")
        btn_clear = QPushButton("Clear")
        for b in (btn_add, btn_add_folder, btn_remove, btn_clear):
            btn_row.addWidget(b)
        left.addLayout(btn_row)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(QSize(THUMB, THUMB))
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        left.addWidget(self.list_widget, stretch=1)

        self.count_label = QLabel("0 photos added")
        left.addWidget(self.count_label)

        root.addLayout(left, stretch=1)

        # -- middle: result / status --------------------------------------
        middle = QVBoxLayout()
        middle.addWidget(QLabel("Result"))
        self.preview_label = QLabel("Add photos, then click Auto-Stack")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setWordWrap(True)
        self.preview_label.setMinimumSize(360, 360)
        self.preview_label.setStyleSheet("background-color: #3a3a3d; border: 1px solid #555;")
        middle.addWidget(self.preview_label, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        middle.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        middle.addWidget(self.progress_bar)

        root.addLayout(middle, stretch=2)

        # -- right: options --------------------------------------------------
        right = QVBoxLayout()
        options_box = QGroupBox("Options")
        form = QFormLayout(options_box)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(MODE_LABELS.keys())
        form.addRow("Scene type:", self.mode_combo)

        self.size_combo = QComboBox()
        self.size_combo.addItems(WORKING_SIZE_LABELS.keys())
        self.size_combo.setCurrentText("2000 px (recommended)")
        form.addRow("Working size:", self.size_combo)

        right.addWidget(options_box)
        right.addStretch(1)

        self.btn_run = QPushButton("Auto-Stack")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        right.addWidget(self.btn_run)
        right.addWidget(self.btn_cancel)

        save_row = QHBoxLayout()
        self.btn_save = QPushButton("Save As...")
        self.btn_save.setEnabled(False)
        self.btn_close = QPushButton("Close")
        save_row.addWidget(self.btn_save)
        save_row.addWidget(self.btn_close)
        right.addLayout(save_row)

        right_container = QWidget()
        right_container.setLayout(right)
        right_container.setMinimumWidth(280)
        root.addWidget(right_container, stretch=1)

        btn_add.clicked.connect(self._add_files_dialog)
        btn_add_folder.clicked.connect(self._add_folder_dialog)
        btn_remove.clicked.connect(self._remove_selected)
        btn_clear.clicked.connect(self._clear_all)
        self.btn_run.clicked.connect(self._run_stitch)
        self.btn_cancel.clicked.connect(self._cancel_stitch)
        self.btn_save.clicked.connect(self._save_as)
        self.btn_close.clicked.connect(self.close)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------
    def add_paths(self, paths: list[str]) -> None:
        existing = {
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        }
        for path in paths:
            if Path(path).suffix.lower() not in IMAGE_EXTENSIONS or path in existing:
                continue
            existing.add(path)
            item = QListWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)

            worker = _ThumbWorker(path)
            worker.signals.ready.connect(self._on_thumb_ready)
            worker.signals.failed.connect(self._on_thumb_failed)
            self._pool.start(worker)
        self._update_count()

    def _item_for_path(self, path: str) -> QListWidgetItem | None:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                return item
        return None

    def _on_thumb_ready(self, path: str, qimage: QImage) -> None:
        item = self._item_for_path(path)
        if item is not None:
            item.setIcon(QIcon(QPixmap.fromImage(qimage)))

    def _on_thumb_failed(self, path: str) -> None:
        item = self._item_for_path(path)
        if item is not None:
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_count()

    def _add_files_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Images", "", f"Images ({exts})")
        if paths:
            self.add_paths(paths)

    def _add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if not folder:
            return
        paths = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
        if paths:
            self.add_paths(paths)

    def _remove_selected(self) -> None:
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))
        self._update_count()

    def _clear_all(self) -> None:
        self.list_widget.clear()
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.setText(f"{self.list_widget.count()} photos added")

    def _ordered_paths(self) -> list[str]:
        return [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]

    # ------------------------------------------------------------------
    # Stitching
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self.btn_run.setVisible(not busy)
        self.btn_cancel.setVisible(busy)
        self.progress_bar.setVisible(busy)
        self.mode_combo.setEnabled(not busy)
        self.size_combo.setEnabled(not busy)
        self.btn_save.setEnabled(not busy and self._result is not None)

    def _run_stitch(self) -> None:
        paths = self._ordered_paths()
        if len(paths) < 2:
            QMessageBox.information(self, "Auto-Stack", "Add at least two overlapping photos first.")
            return

        mode = MODE_LABELS[self.mode_combo.currentText()]
        max_dim = WORKING_SIZE_LABELS[self.size_combo.currentText()]
        options = AutoStackOptions(mode=mode, max_working_dim=max_dim)

        self._result = None
        self.preview_label.setText("")
        self.preview_label.setPixmap(QPixmap())
        self.status_label.setText(f"Loading 0 / {len(paths)} photos...")
        self.progress_bar.setRange(0, len(paths))
        self.progress_bar.setValue(0)
        self._set_busy(True)

        self._worker = AutoStackWorker(paths, options, self)
        self._worker.loadProgress.connect(self._on_load_progress)
        self._worker.stitchingStarted.connect(self._on_stitching_started)
        self._worker.finishedStack.connect(self._on_stitch_done)
        self._worker.failed.connect(self._on_stitch_failed)
        self._worker.start()

    def _cancel_stitch(self) -> None:
        if self._worker is not None:
            self._worker.requestInterruption()
        self.status_label.setText("Cancelling...")

    def _on_load_progress(self, done: int, total: int, path: str) -> None:
        self.progress_bar.setValue(done)
        self.status_label.setText(f"Loading {done} / {total}: {Path(path).name}")

    def _on_stitching_started(self) -> None:
        self.progress_bar.setRange(0, 0)  # indeterminate: OpenCV reports no progress here
        self.status_label.setText(
            "Matching patterns and blending - this can take a while for many photos..."
        )

    def _on_stitch_done(self, result) -> None:
        self._result = result
        self._set_busy(False)
        self.status_label.setText(f"Done - {result.width} x {result.height} px")
        self._render_preview()

    def _on_stitch_failed(self, message: str) -> None:
        self._result = None
        self._set_busy(False)
        self.status_label.setText("Failed.")
        self.preview_label.setText("Add photos, then click Auto-Stack")
        QMessageBox.warning(self, "Auto-Stack", message)

    def _render_preview(self) -> None:
        if self._result is None:
            return
        pixmap = pil_to_qpixmap(self._result)
        scaled = pixmap.scaled(
            self.preview_label.width() - 10, self.preview_label.height() - 10,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_preview()

    def _save_as(self) -> None:
        if self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Stitched Image", "autostack.jpg",
            "JPEG (*.jpg *.jpeg);;PNG (*.png);;TIFF (*.tiff);;WEBP (*.webp)",
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            result = self._result
            if ext in (".jpg", ".jpeg"):
                result = result.convert("RGB")
                result.save(path, quality=95, optimize=True)
            else:
                result.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Auto-Stack", f"Could not save the image:\n{exc}")
            return
        QMessageBox.information(self, "Auto-Stack", f"Saved {path}")

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(3000)
        super().closeEvent(event)
