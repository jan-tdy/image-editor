"""Conversion helpers between Pillow images and Qt pixmaps."""
from __future__ import annotations

from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def pil_to_qimage(image: Image.Image) -> QImage:
    if image.mode not in ("RGBA", "RGB"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")
    data = image.tobytes("raw", image.mode)
    bytes_per_pixel = 4 if image.mode == "RGBA" else 3
    bytes_per_line = image.width * bytes_per_pixel
    fmt = QImage.Format.Format_RGBA8888 if image.mode == "RGBA" else QImage.Format.Format_RGB888
    # Pillow's tobytes() is tightly packed (no scanline padding), so the
    # stride must be passed explicitly - QImage's no-stride constructor
    # assumes rows are padded to a 4-byte boundary, which silently misreads
    # RGB888 data whenever width isn't a multiple of 4.
    qimg = QImage(data, image.width, image.height, bytes_per_line, fmt)
    # Copy so the QImage owns its buffer independent of Pillow's memory.
    return qimg.copy()


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(image))


def make_thumbnail_pixmap(image: Image.Image, size: int) -> QPixmap:
    thumb = image.copy()
    thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
    pix = pil_to_qpixmap(thumb)
    return pix


def make_thumbnail_qimage(image: Image.Image, size: int) -> QImage:
    """Like make_thumbnail_pixmap, but returns a QImage. QPixmap is a GUI
    class Qt says must only be constructed on the main thread; QImage is
    safe to build off-thread, so background workers should use this and let
    the receiving (main-thread) slot build the QPixmap."""
    thumb = image.copy()
    thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
    return pil_to_qimage(thumb)
