"""Main application window: menus, toolbar, and wiring between widgets."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QSettings, QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolBar,
    QWidget,
)

from .constants import APP_NAME, APP_ORG, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .core.convert import pil_to_qpixmap
from .core.image_document import ImageDocument
from .dialogs.batch_dialog import BatchDialog
from .dialogs.stitch_dialog import StitchDialog
from .models.file_model import FolderNavigator
from .widgets.adjustments_panel import AdjustmentsPanel
from .widgets.image_view import ImageView
from .widgets.thumbnail_panel import ThumbnailPanel
from .widgets.video_view import MULTIMEDIA_AVAILABLE, VideoView

try:
    from send2trash import send2trash
except Exception:  # pragma: no cover - optional dependency
    send2trash = None

SAVE_FILTERS = "JPEG (*.jpg *.jpeg);;PNG (*.png);;BMP (*.bmp);;TIFF (*.tiff);;WEBP (*.webp)"
SLIDESHOW_INTERVALS = {"2 seconds": 2, "3 seconds": 3, "5 seconds": 5, "10 seconds": 10}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        self.settings = QSettings(APP_ORG, APP_NAME)
        self.navigator = FolderNavigator()
        self.document: ImageDocument | None = None
        self.is_video = False
        self._suspend_thumb_sync = False

        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self._slideshow_step)
        self.slideshow_interval_s = 3

        self._build_central_widgets()
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._update_actions_enabled()

        last_folder = self.settings.value("last_folder", "", str)
        if last_folder and os.path.isdir(last_folder):
            self.open_folder(last_folder)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_central_widgets(self) -> None:
        self.image_view = ImageView()
        self.image_view.zoomChanged.connect(self._on_zoom_changed)
        self.image_view.cropCommitted.connect(self._on_crop_committed)
        self.image_view.cropRectChanged.connect(self._on_crop_rect_changed)

        self.video_view = VideoView()
        if MULTIMEDIA_AVAILABLE:
            self.video_view.playbackError.connect(
                lambda msg: self.statusBar().showMessage(f"Playback error: {msg}", 5000)
            )

        self.stack = QStackedWidget()
        self.stack.addWidget(self.image_view)
        self.stack.addWidget(self.video_view)
        self.setCentralWidget(self.stack)

    def _build_docks(self) -> None:
        self.thumbnail_panel = ThumbnailPanel()
        self.thumbnail_panel.fileActivated.connect(self._on_thumbnail_activated)
        self.thumbnail_panel.currentFileChanged.connect(self._on_thumbnail_current_changed)

        self.browser_dock = QDockWidget("Browser", self)
        self.browser_dock.setObjectName("browser_dock")
        self.browser_dock.setWidget(self.thumbnail_panel)
        self.browser_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.browser_dock)

        self.adjustments_panel = AdjustmentsPanel()
        self.adjustments_panel.adjustmentChanged.connect(self._on_adjustment_changed)
        self.adjustments_panel.applyRequested.connect(self._on_adjustments_apply)
        self.adjustments_panel.resetRequested.connect(self._on_adjustments_reset)
        self.adjustments_panel.cancelRequested.connect(self._on_adjustments_cancel)

        self.adjust_dock = QDockWidget("Adjustments", self)
        self.adjust_dock.setObjectName("adjust_dock")
        self.adjust_dock.setWidget(self.adjustments_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.adjust_dock)
        self.adjust_dock.hide()
        self.adjust_dock.visibilityChanged.connect(self._on_adjust_dock_visibility)

    def _icon(self, standard) -> QIcon:
        return self.style().standardIcon(standard)

    def _build_actions(self) -> None:
        style = QStyle.StandardPixmap

        self.act_open_file = QAction(self._icon(style.SP_FileIcon), "Open File...", self)
        self.act_open_file.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open_file.triggered.connect(self.open_file_dialog)

        self.act_open_folder = QAction(self._icon(style.SP_DirOpenIcon), "Open Folder...", self)
        self.act_open_folder.setShortcut("Ctrl+Shift+O")
        self.act_open_folder.triggered.connect(self.open_folder_dialog)

        self.act_save = QAction(self._icon(style.SP_DialogSaveButton), "Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.save_current)

        self.act_save_as = QAction("Save As...", self)
        self.act_save_as.setShortcut("Ctrl+Shift+S")
        self.act_save_as.triggered.connect(self.save_current_as)

        self.act_revert = QAction("Revert to Original", self)
        self.act_revert.triggered.connect(self.revert_current)

        self.act_rename = QAction("Rename...", self)
        self.act_rename.setShortcut("F2")
        self.act_rename.triggered.connect(self.rename_current)

        self.act_delete = QAction(self._icon(style.SP_TrashIcon), "Delete File...", self)
        self.act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.act_delete.triggered.connect(self.delete_current)

        self.act_exit = QAction("Exit", self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)

        self.act_undo = QAction(self._icon(style.SP_ArrowBack), "Undo", self)
        self.act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.act_undo.triggered.connect(self.undo)

        self.act_redo = QAction(self._icon(style.SP_ArrowForward), "Redo", self)
        self.act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.act_redo.triggered.connect(self.redo)

        self.act_rotate_left = QAction("Rotate Left", self)
        self.act_rotate_left.setShortcut("Ctrl+L")
        self.act_rotate_left.triggered.connect(lambda: self.rotate(clockwise=False))

        self.act_rotate_right = QAction("Rotate Right", self)
        self.act_rotate_right.setShortcut("Ctrl+R")
        self.act_rotate_right.triggered.connect(lambda: self.rotate(clockwise=True))

        self.act_flip_h = QAction("Flip Horizontal", self)
        self.act_flip_h.setShortcut("H")
        self.act_flip_h.triggered.connect(self.flip_horizontal)

        self.act_flip_v = QAction("Flip Vertical", self)
        self.act_flip_v.setShortcut("V")
        self.act_flip_v.triggered.connect(self.flip_vertical)

        self.act_crop = QAction("Crop", self)
        self.act_crop.setShortcut("C")
        self.act_crop.setCheckable(True)
        self.act_crop.triggered.connect(self.toggle_crop)

        self.act_crop_apply = QAction("Apply Crop", self)
        self.act_crop_apply.setShortcut("Return")
        self.act_crop_apply.triggered.connect(self.image_view.commit_crop)
        self.act_crop_apply.setEnabled(False)

        self.act_crop_cancel = QAction("Cancel Crop", self)
        self.act_crop_cancel.setShortcut("Escape")
        self.act_crop_cancel.triggered.connect(self.cancel_crop)
        self.act_crop_cancel.setEnabled(False)

        self.act_adjustments = QAction("Adjustments...", self)
        self.act_adjustments.setShortcut("Ctrl+U")
        self.act_adjustments.setCheckable(True)
        self.act_adjustments.triggered.connect(self.toggle_adjustments)

        self.act_zoom_in = QAction(self._icon(style.SP_ArrowUp), "Zoom In", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.triggered.connect(self.image_view.zoom_in)

        self.act_zoom_out = QAction(self._icon(style.SP_ArrowDown), "Zoom Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.triggered.connect(self.image_view.zoom_out)

        self.act_zoom_fit = QAction("Fit to Window", self)
        self.act_zoom_fit.setShortcut("Ctrl+0")
        self.act_zoom_fit.triggered.connect(self.image_view.fit_to_window)

        self.act_zoom_100 = QAction("Actual Size (100%)", self)
        self.act_zoom_100.setShortcut("Ctrl+1")
        self.act_zoom_100.triggered.connect(self.image_view.reset_zoom)

        self.act_fullscreen = QAction("Fullscreen", self)
        self.act_fullscreen.setShortcut("F11")
        self.act_fullscreen.setCheckable(True)
        self.act_fullscreen.triggered.connect(self.toggle_fullscreen)

        self.act_toggle_browser = self.browser_dock.toggleViewAction()
        self.act_toggle_browser.setText("Browser Panel")

        self.act_slideshow = QAction("Start Slideshow", self)
        self.act_slideshow.setShortcut("F5")
        self.act_slideshow.setCheckable(True)
        self.act_slideshow.triggered.connect(self.toggle_slideshow)

        self.act_prev = QAction(self._icon(style.SP_MediaSeekBackward), "Previous", self)
        self.act_prev.setShortcut("Left")
        self.act_prev.triggered.connect(self.go_previous)

        self.act_next = QAction(self._icon(style.SP_MediaSeekForward), "Next", self)
        self.act_next.setShortcut("Right")
        self.act_next.triggered.connect(self.go_next)

        self.act_batch = QAction("Batch Rename && Edit...", self)
        self.act_batch.setShortcut("Ctrl+B")
        self.act_batch.triggered.connect(self.open_batch_dialog)

        self.act_stitch = QAction("Join Images...", self)
        self.act_stitch.setShortcut("Ctrl+J")
        self.act_stitch.triggered.connect(self.open_stitch_dialog)

        self.act_about = QAction("About", self)
        self.act_about.triggered.connect(self.show_about)

        self.slideshow_interval_actions = QActionGroup(self)
        self.slideshow_interval_actions.setExclusive(True)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction(self.act_open_file)
        file_menu.addAction(self.act_open_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addAction(self.act_revert)
        file_menu.addSeparator()
        file_menu.addAction(self.act_rename)
        file_menu.addAction(self.act_delete)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        edit_menu = menubar.addMenu("&Edit")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_rotate_left)
        edit_menu.addAction(self.act_rotate_right)
        edit_menu.addAction(self.act_flip_h)
        edit_menu.addAction(self.act_flip_v)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_crop)
        edit_menu.addAction(self.act_crop_apply)
        edit_menu.addAction(self.act_crop_cancel)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_adjustments)

        view_menu = menubar.addMenu("&View")
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_zoom_fit)
        view_menu.addAction(self.act_zoom_100)
        view_menu.addSeparator()
        view_menu.addAction(self.act_fullscreen)
        view_menu.addAction(self.act_toggle_browser)
        view_menu.addSeparator()
        slideshow_menu = view_menu.addMenu("Slideshow Interval")
        for label, seconds in SLIDESHOW_INTERVALS.items():
            action = QAction(label, self, checkable=True)
            action.setChecked(seconds == self.slideshow_interval_s)
            action.triggered.connect(lambda _checked, s=seconds: self._set_slideshow_interval(s))
            self.slideshow_interval_actions.addAction(action)
            slideshow_menu.addAction(action)
        view_menu.addAction(self.act_slideshow)

        nav_menu = menubar.addMenu("&Navigate")
        nav_menu.addAction(self.act_prev)
        nav_menu.addAction(self.act_next)

        tools_menu = menubar.addMenu("&Tools")
        tools_menu.addAction(self.act_batch)
        tools_menu.addAction(self.act_stitch)

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setIconSize(QSize(22, 22))
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for action in (
            self.act_open_file,
            self.act_open_folder,
            self.act_save,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.act_prev, self.act_next):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.act_undo, self.act_redo):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.act_rotate_left, self.act_rotate_right, self.act_flip_h, self.act_flip_v, self.act_crop):
            toolbar.addAction(action)
        toolbar.addSeparator()
        for action in (self.act_zoom_out, self.act_zoom_fit, self.act_zoom_in):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_adjustments)
        toolbar.addAction(self.act_slideshow)
        toolbar.addAction(self.act_fullscreen)
        toolbar.addSeparator()
        toolbar.addAction(self.act_batch)
        toolbar.addAction(self.act_stitch)

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        self.path_label = QLabel("No file open")
        self.size_label = QLabel("")
        self.zoom_label = QLabel("")
        bar.addWidget(self.path_label, stretch=1)
        bar.addPermanentWidget(self.size_label)
        bar.addPermanentWidget(self.zoom_label)

    # ------------------------------------------------------------------
    # Opening files / folders
    # ------------------------------------------------------------------
    def open_file_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(self, "Open File", "", f"Media Files ({exts})")
        if path:
            self.open_folder(str(Path(path).parent), select_path=path)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")
        if folder:
            self.open_folder(folder)

    def open_folder(self, folder: str, select_path: str | None = None) -> None:
        self.navigator.set_folder(folder, select_path=select_path)
        self.thumbnail_panel.load_folder(folder)
        self.settings.setValue("last_folder", folder)
        entry = self.navigator.current()
        if entry:
            self.open_media(entry.path, sync_thumbnail=True)
        else:
            self._clear_view()
            self.statusBar().showMessage("No images or videos found in this folder", 4000)

    def open_media(self, path: str, sync_thumbnail: bool = True) -> None:
        ext = Path(path).suffix.lower()
        try:
            if ext in VIDEO_EXTENSIONS:
                self._open_video(path)
            else:
                self._open_image(path)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            QMessageBox.warning(self, "Could not open file", f"{path}\n\n{exc}")
            return

        self.navigator.select(path)
        if sync_thumbnail:
            self._suspend_thumb_sync = True
            self.thumbnail_panel.select_path(path)
            self._suspend_thumb_sync = False
        self._update_actions_enabled()

    def _open_image(self, path: str) -> None:
        if self.is_video:
            self.video_view.stop_and_release()
        self.is_video = False
        self.stack.setCurrentWidget(self.image_view)
        self.document = ImageDocument(path)
        self.adjustments_panel.set_values(brightness=0, contrast=0, saturation=0, red=0, green=0, blue=0)
        self.refresh_view()
        self._update_status(path)

    def _open_video(self, path: str) -> None:
        self.document = None
        self.is_video = True
        self.stack.setCurrentWidget(self.video_view)
        self.video_view.load(path)
        self._update_status(path, is_video=True)

    def _clear_view(self) -> None:
        self.document = None
        self.is_video = False
        self.image_view.clear()
        self.path_label.setText("No file open")
        self.size_label.setText("")
        self.zoom_label.setText("")
        self.setWindowTitle(APP_NAME)

    def _update_status(self, path: str, is_video: bool = False) -> None:
        self.path_label.setText(path)
        self.setWindowTitle(f"{Path(path).name} - {APP_NAME}")
        if is_video or self.document is None:
            self.size_label.setText("")
        else:
            w, h = self.document.size
            self.size_label.setText(f"{w} x {h}px")

    # -- thumbnail panel sync -------------------------------------------------
    def _on_thumbnail_activated(self, path: str) -> None:
        self.open_media(path, sync_thumbnail=False)

    def _on_thumbnail_current_changed(self, path: str) -> None:
        if self._suspend_thumb_sync:
            return
        self.open_media(path, sync_thumbnail=False)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def refresh_view(self) -> None:
        if self.document is None:
            return
        pixmap: QPixmap = pil_to_qpixmap(self.document.preview_image())
        self.image_view.set_pixmap(pixmap)
        w, h = self.document.size
        self.size_label.setText(f"{w} x {h}px")
        self._update_actions_enabled()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{zoom * 100:.0f}%")

    # ------------------------------------------------------------------
    # Edit operations
    # ------------------------------------------------------------------
    def _guard_image(self) -> bool:
        if self.document is None or self.is_video:
            return False
        return True

    def undo(self) -> None:
        if self._guard_image() and self.document.undo():
            self.refresh_view()

    def redo(self) -> None:
        if self._guard_image() and self.document.redo():
            self.refresh_view()

    def rotate(self, clockwise: bool) -> None:
        if not self._guard_image():
            return
        self.document.rotate90(clockwise=clockwise)
        self.refresh_view()

    def flip_horizontal(self) -> None:
        if not self._guard_image():
            return
        self.document.flip_horizontal()
        self.refresh_view()

    def flip_vertical(self) -> None:
        if not self._guard_image():
            return
        self.document.flip_vertical()
        self.refresh_view()

    def toggle_crop(self, checked: bool) -> None:
        if not self._guard_image():
            self.act_crop.setChecked(False)
            return
        if checked:
            self.image_view.enter_crop_mode()
        else:
            self.image_view.exit_crop_mode()
        self.act_crop_apply.setEnabled(checked)
        self.act_crop_cancel.setEnabled(checked)

    def cancel_crop(self) -> None:
        self.act_crop.setChecked(False)
        self.image_view.exit_crop_mode()
        self.act_crop_apply.setEnabled(False)
        self.act_crop_cancel.setEnabled(False)

    def _on_crop_rect_changed(self, rect) -> None:
        pass  # reserved for a future live crop-size readout

    def _on_crop_committed(self, box: tuple[int, int, int, int]) -> None:
        if not self._guard_image():
            return
        self.document.crop(box)
        self.refresh_view()
        self.act_crop.setChecked(False)
        self.act_crop_apply.setEnabled(False)
        self.act_crop_cancel.setEnabled(False)

    def toggle_adjustments(self, checked: bool) -> None:
        self.adjust_dock.setVisible(checked)

    def _on_adjust_dock_visibility(self, visible: bool) -> None:
        self.act_adjustments.setChecked(visible)
        if not visible and self.document is not None:
            self.document.reset_adjustments()
            self.refresh_view()

    def _on_adjustment_changed(self, name: str, value: float) -> None:
        if not self._guard_image():
            return
        self.document.set_adjustments(**{name: value})
        self.refresh_view()

    def _on_adjustments_apply(self) -> None:
        if not self._guard_image():
            return
        self.document.commit_adjustments()
        self.adjustments_panel.set_values(brightness=0, contrast=0, saturation=0, red=0, green=0, blue=0)
        self.refresh_view()

    def _on_adjustments_reset(self) -> None:
        if not self._guard_image():
            return
        self.document.reset_adjustments()
        self.refresh_view()

    def _on_adjustments_cancel(self) -> None:
        self._on_adjustments_reset()
        self.adjust_dock.hide()

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------
    def save_current(self) -> None:
        if not self._guard_image():
            return
        try:
            self.document.save()
            self.statusBar().showMessage(f"Saved {self.document.path}", 3000)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))

    def save_current_as(self) -> None:
        if not self._guard_image():
            return
        start = self.document.path or ""
        path, _ = QFileDialog.getSaveFileName(self, "Save Image As", start, SAVE_FILTERS)
        if not path:
            return
        try:
            self.document.save(path)
            self.statusBar().showMessage(f"Saved {path}", 3000)
            self.navigator.refresh()
            self.thumbnail_panel.load_folder(self.navigator.folder)
            self.thumbnail_panel.select_path(path)
            self._update_status(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Save failed", str(exc))

    def revert_current(self) -> None:
        if not self._guard_image():
            return
        if QMessageBox.question(
            self, "Revert to Original", "Discard all edits and revert to the original file?"
        ) == QMessageBox.StandardButton.Yes:
            self.document.revert_to_original()
            self.refresh_view()

    def rename_current(self) -> None:
        entry = self.navigator.current()
        if entry is None:
            return
        old_path = Path(entry.path)
        new_name, ok = QInputDialog.getText(self, "Rename File", "New name:", text=old_path.stem)
        if not ok or not new_name.strip():
            return
        new_path = old_path.with_name(new_name.strip() + old_path.suffix)
        if new_path.exists():
            QMessageBox.warning(self, "Rename failed", f"{new_path.name} already exists.")
            return
        try:
            old_path.rename(new_path)
        except OSError as exc:
            QMessageBox.critical(self, "Rename failed", str(exc))
            return
        if self.document is not None and self.document.path == str(old_path):
            self.document.path = str(new_path)
        self.navigator.refresh()
        self.thumbnail_panel.load_folder(self.navigator.folder)
        self.open_media(str(new_path), sync_thumbnail=True)

    def delete_current(self) -> None:
        entry = self.navigator.current()
        if entry is None:
            return
        verb = "move to the trash" if send2trash else "permanently delete"
        if QMessageBox.question(
            self, "Delete File", f"Are you sure you want to {verb}:\n{entry.name}?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            if send2trash:
                send2trash(entry.path)
            else:
                os.remove(entry.path)
        except OSError as exc:
            QMessageBox.critical(self, "Delete failed", str(exc))
            return

        folder = self.navigator.folder
        self.navigator.refresh()
        self.thumbnail_panel.load_folder(folder)
        next_entry = self.navigator.current()
        if next_entry:
            self.open_media(next_entry.path, sync_thumbnail=True)
        else:
            self._clear_view()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def go_next(self) -> None:
        entry = self.navigator.next()
        if entry:
            self.open_media(entry.path)

    def go_previous(self) -> None:
        entry = self.navigator.prev()
        if entry:
            self.open_media(entry.path)

    # ------------------------------------------------------------------
    # View
    # ------------------------------------------------------------------
    def toggle_fullscreen(self, checked: bool) -> None:
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    def _set_slideshow_interval(self, seconds: int) -> None:
        self.slideshow_interval_s = seconds
        if self.slideshow_timer.isActive():
            self.slideshow_timer.setInterval(seconds * 1000)

    def toggle_slideshow(self, checked: bool) -> None:
        if checked:
            self.slideshow_timer.start(self.slideshow_interval_s * 1000)
            self.act_slideshow.setText("Stop Slideshow")
        else:
            self.slideshow_timer.stop()
            self.act_slideshow.setText("Start Slideshow")

    def _slideshow_step(self) -> None:
        entry = self.navigator.next()
        if entry is None:
            if not self.navigator.entries:
                self.toggle_slideshow(False)
                self.act_slideshow.setChecked(False)
                return
            self.navigator.index = -1
            entry = self.navigator.next()
        if entry:
            self.open_media(entry.path)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _update_actions_enabled(self) -> None:
        has_image = self._guard_image()
        has_file = self.document is not None or self.is_video
        for action in (
            self.act_save, self.act_save_as, self.act_revert,
            self.act_rotate_left, self.act_rotate_right,
            self.act_flip_h, self.act_flip_v, self.act_crop, self.act_adjustments,
        ):
            action.setEnabled(has_image)
        self.act_undo.setEnabled(has_image and self.document.can_undo())
        self.act_redo.setEnabled(has_image and self.document.can_redo())
        self.act_delete.setEnabled(has_file)
        self.act_rename.setEnabled(has_file)
        self.act_prev.setEnabled(self.navigator.has_prev())
        self.act_next.setEnabled(self.navigator.has_next())

    # ------------------------------------------------------------------
    # Tools: batch editing / image joining
    # ------------------------------------------------------------------
    def open_batch_dialog(self) -> None:
        initial_paths = [e.path for e in self.navigator.entries] if self.navigator.entries else None
        dialog = BatchDialog(self, initial_paths=initial_paths)
        dialog.exec()
        self._reload_after_external_change()

    def open_stitch_dialog(self) -> None:
        initial_paths = [
            e.path for e in self.navigator.entries if Path(e.path).suffix.lower() in IMAGE_EXTENSIONS
        ] if self.navigator.entries else None
        dialog = StitchDialog(self, initial_paths=initial_paths)
        dialog.exec()
        self._reload_after_external_change()

    def _reload_after_external_change(self) -> None:
        """Batch operations can rename/move/delete files outside our control;
        resync the navigator, thumbnails and the currently open document."""
        if not self.navigator.folder:
            return
        current_path = self.document.path if self.document else (
            self.navigator.current().path if self.navigator.current() else None
        )
        self.navigator.refresh()
        self.thumbnail_panel.load_folder(self.navigator.folder)
        if current_path and os.path.exists(current_path):
            self.open_media(current_path, sync_thumbnail=True)
        else:
            entry = self.navigator.current()
            if entry:
                self.open_media(entry.path, sync_thumbnail=True)
            else:
                self._clear_view()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME}</h3>"
            "<p>A fast PyQt6 image &amp; video viewer/editor.</p>"
            "<p>Browse folders, view images and videos, rotate/flip/crop, "
            "and adjust brightness, contrast, saturation and RGB channels. "
            "Batch rename/convert/resize/adjust and an image-joining tool "
            "are available under Tools.</p>",
        )

    # -- drag & drop -----------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        local_path = urls[0].toLocalFile()
        if os.path.isdir(local_path):
            self.open_folder(local_path)
        elif os.path.isfile(local_path):
            self.open_folder(str(Path(local_path).parent), select_path=local_path)

    def closeEvent(self, event) -> None:
        self.slideshow_timer.stop()
        self.settings.setValue("last_folder", self.navigator.folder or "")
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
