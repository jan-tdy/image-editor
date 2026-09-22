"""Zoom/pan image viewer with an interactive crop-rectangle tool."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from ..constants import ZOOM_MAX, ZOOM_MIN, ZOOM_STEP

HANDLE_SIZE = 10
HANDLES = ("tl", "t", "tr", "l", "r", "bl", "b", "br")


class ImageView(QGraphicsView):
    zoomChanged = pyqtSignal(float)
    cropRectChanged = pyqtSignal(object)  # QRectF or None
    cropCommitted = pyqtSignal(tuple)  # (left, top, right, bottom) ints
    panRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(45, 45, 48)))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._zoom = 1.0
        self._fit_mode = True

        self.crop_mode = False
        self._crop_rect_item: QGraphicsRectItem | None = None
        self._crop_handles: dict[str, QGraphicsRectItem] = {}
        self._drag_mode = None  # None | "new" | "move" | handle name
        self._drag_origin = QPointF()
        self._rect_at_drag_start = QRectF()

    # -- image loading --------------------------------------------------
    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._scene.clear()
        self._crop_rect_item = None
        self._crop_handles.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        if self._fit_mode:
            self.fit_to_window()

    def clear(self) -> None:
        self._scene.clear()
        self._pixmap_item = None
        self._crop_rect_item = None
        self._crop_handles.clear()

    def image_rect(self) -> QRectF:
        if self._pixmap_item is None:
            return QRectF()
        return QRectF(self._pixmap_item.pixmap().rect())

    # -- zoom -------------------------------------------------------------
    def fit_to_window(self) -> None:
        if self._pixmap_item is None:
            return
        self._fit_mode = True
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self.zoomChanged.emit(self._zoom)

    def reset_zoom(self) -> None:
        self._fit_mode = False
        self.resetTransform()
        self._zoom = 1.0
        self.zoomChanged.emit(self._zoom)

    def set_zoom(self, factor: float, anchor_point: QPointF | None = None) -> None:
        if self._pixmap_item is None:
            return
        factor = max(ZOOM_MIN, min(ZOOM_MAX, factor))
        self._fit_mode = False
        scale = factor / self._zoom if self._zoom else factor
        self.scale(scale, scale)
        self._zoom = factor
        self.zoomChanged.emit(self._zoom)

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / ZOOM_STEP)

    @property
    def zoom(self) -> float:
        return self._zoom

    def wheelEvent(self, event):
        if self._pixmap_item is None:
            return super().wheelEvent(event)
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = ZOOM_STEP if delta > 0 else 1 / ZOOM_STEP
        self.set_zoom(self._zoom * factor)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_mode and self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

    # -- crop tool ----------------------------------------------------------
    def enter_crop_mode(self) -> None:
        if self._pixmap_item is None:
            return
        self.crop_mode = True
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(Qt.CursorShape.CrossCursor)
        if self._crop_rect_item is None:
            rect = self.image_rect()
            margin_x, margin_y = rect.width() * 0.1, rect.height() * 0.1
            self._set_crop_rect(rect.adjusted(margin_x, margin_y, -margin_x, -margin_y))

    def exit_crop_mode(self, keep_rect: bool = False) -> None:
        self.crop_mode = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.unsetCursor()
        if not keep_rect:
            self._remove_crop_items()
        self.cropRectChanged.emit(None)

    def _remove_crop_items(self) -> None:
        if self._crop_rect_item is not None:
            self._scene.removeItem(self._crop_rect_item)
            self._crop_rect_item = None
        for handle in self._crop_handles.values():
            self._scene.removeItem(handle)
        self._crop_handles.clear()

    def current_crop_rect(self) -> QRectF | None:
        if self._crop_rect_item is None:
            return None
        return self._crop_rect_item.rect()

    def commit_crop(self) -> None:
        rect = self.current_crop_rect()
        if rect is None:
            return
        box = (round(rect.left()), round(rect.top()), round(rect.right()), round(rect.bottom()))
        self.cropCommitted.emit(box)
        self.exit_crop_mode(keep_rect=False)

    def _set_crop_rect(self, rect: QRectF) -> None:
        bounds = self.image_rect()
        rect = rect.normalized().intersected(bounds)
        if rect.width() < 4 or rect.height() < 4:
            return
        if self._crop_rect_item is None:
            pen = QPen(QColor(255, 255, 255), 1.5, Qt.PenStyle.DashLine)
            self._crop_rect_item = self._scene.addRect(rect, pen, QBrush(QColor(0, 0, 0, 0)))
            self._crop_rect_item.setZValue(10)
            for name in HANDLES:
                handle = self._scene.addRect(
                    0, 0, HANDLE_SIZE, HANDLE_SIZE,
                    QPen(QColor(30, 30, 30)), QBrush(QColor(255, 255, 255)),
                )
                handle.setZValue(11)
                self._crop_handles[name] = handle
        else:
            self._crop_rect_item.setRect(rect)
        self._position_handles(rect)
        self.cropRectChanged.emit(rect)

    def _position_handles(self, rect: QRectF) -> None:
        half = HANDLE_SIZE / 2
        positions = {
            "tl": rect.topLeft(), "t": QPointF(rect.center().x(), rect.top()),
            "tr": rect.topRight(), "l": QPointF(rect.left(), rect.center().y()),
            "r": QPointF(rect.right(), rect.center().y()), "bl": rect.bottomLeft(),
            "b": QPointF(rect.center().x(), rect.bottom()), "br": rect.bottomRight(),
        }
        for name, pos in positions.items():
            handle = self._crop_handles.get(name)
            if handle:
                handle.setPos(pos.x() - half, pos.y() - half)

    def _handle_at(self, scene_pos: QPointF) -> str | None:
        for name, handle in self._crop_handles.items():
            if handle.sceneBoundingRect().adjusted(-4, -4, 4, 4).contains(scene_pos):
                return name
        return None

    # -- mouse handling -------------------------------------------------------
    def mousePressEvent(self, event):
        if not self.crop_mode or self._pixmap_item is None:
            return super().mousePressEvent(event)
        pos = self.mapToScene(event.pos())
        handle = self._handle_at(pos)
        rect = self.current_crop_rect()
        if handle:
            self._drag_mode = handle
        elif rect is not None and rect.contains(pos):
            self._drag_mode = "move"
        else:
            self._drag_mode = "new"
            self._set_crop_rect(QRectF(pos, pos))
        self._drag_origin = pos
        self._rect_at_drag_start = self.current_crop_rect() or QRectF(pos, pos)
        event.accept()

    def mouseMoveEvent(self, event):
        if not self.crop_mode or self._drag_mode is None:
            return super().mouseMoveEvent(event)
        pos = self.mapToScene(event.pos())
        rect = QRectF(self._rect_at_drag_start)
        dx, dy = pos.x() - self._drag_origin.x(), pos.y() - self._drag_origin.y()

        if self._drag_mode == "new":
            self._set_crop_rect(QRectF(self._drag_origin, pos))
        elif self._drag_mode == "move":
            bounds = self.image_rect()
            moved = rect.translated(dx, dy)
            if moved.left() < bounds.left():
                moved.moveLeft(bounds.left())
            if moved.top() < bounds.top():
                moved.moveTop(bounds.top())
            if moved.right() > bounds.right():
                moved.moveRight(bounds.right())
            if moved.bottom() > bounds.bottom():
                moved.moveBottom(bounds.bottom())
            self._set_crop_rect(moved)
        else:
            if "l" in self._drag_mode:
                rect.setLeft(rect.left() + dx)
            if "r" in self._drag_mode:
                rect.setRight(rect.right() + dx)
            if "t" in self._drag_mode:
                rect.setTop(rect.top() + dy)
            if "b" in self._drag_mode:
                rect.setBottom(rect.bottom() + dy)
            self._set_crop_rect(rect)
        event.accept()

    def mouseReleaseEvent(self, event):
        if not self.crop_mode:
            return super().mouseReleaseEvent(event)
        self._drag_mode = None
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self.crop_mode:
            self.commit_crop()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
