"""Thumbnail strip for browsing a folder's images and videos."""
from __future__ import annotations

from PyQt6.QtCore import QFileInfo, QObject, QRunnable, QSize, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QFileIconProvider, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..core.convert import make_thumbnail_pixmap
from ..core.image_ops import load_with_orientation
from ..models.file_model import MediaEntry, list_media

THUMB_SIZE = 96


class _ThumbnailSignals(QObject):
    ready = pyqtSignal(str, QPixmap)


class _ThumbnailWorker(QRunnable):
    def __init__(self, path: str):
        super().__init__()
        self.path = path
        self.signals = _ThumbnailSignals()

    def run(self) -> None:
        try:
            image = load_with_orientation(self.path)
            pixmap = make_thumbnail_pixmap(image, THUMB_SIZE)
        except Exception:
            return
        self.signals.ready.emit(self.path, pixmap)


class ThumbnailPanel(QWidget):
    fileActivated = pyqtSignal(str)
    currentFileChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance()
        self._icon_provider = QFileIconProvider()
        self._items: dict[str, QListWidgetItem] = {}
        self._video_icon = self._icon_provider.icon(QFileIconProvider.IconType.File)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self.list_widget.setGridSize(QSize(THUMB_SIZE + 24, THUMB_SIZE + 36))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setSpacing(4)
        self.list_widget.setWordWrap(True)
        self.list_widget.setWrapping(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.list_widget)

        self.list_widget.itemActivated.connect(self._on_activated)
        self.list_widget.itemDoubleClicked.connect(self._on_activated)
        self.list_widget.currentItemChanged.connect(self._on_current_changed)

    def load_folder(self, folder: str) -> list[MediaEntry]:
        entries = list_media(folder)
        self.list_widget.clear()
        self._items.clear()
        for entry in entries:
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry.path)
            item.setToolTip(entry.path)
            if entry.is_video:
                item.setIcon(self._icon_for(entry.path))
            else:
                item.setIcon(QIcon())  # populated asynchronously
            self.list_widget.addItem(item)
            self._items[entry.path] = item
            if not entry.is_video:
                self._queue_thumbnail(entry.path)
        return entries

    def _icon_for(self, path: str) -> QIcon:
        return self._icon_provider.icon(QFileInfo(path))

    def _queue_thumbnail(self, path: str) -> None:
        worker = _ThumbnailWorker(path)
        worker.signals.ready.connect(self._on_thumbnail_ready)
        self._pool.start(worker)

    def _on_thumbnail_ready(self, path: str, pixmap: QPixmap) -> None:
        item = self._items.get(path)
        if item is not None:
            item.setIcon(QIcon(pixmap))

    def select_path(self, path: str) -> None:
        item = self._items.get(path)
        if item is not None:
            self.list_widget.setCurrentItem(item)
            self.list_widget.scrollToItem(item)

    def _on_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.fileActivated.emit(path)

    def _on_current_changed(self, current: QListWidgetItem, _previous) -> None:
        if current is None:
            return
        path = current.data(Qt.ItemDataRole.UserRole)
        if path:
            self.currentFileChanged.emit(path)
