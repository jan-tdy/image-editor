"""Conversion helpers between Pillow images and Qt pixmaps."""
from __future__ import annotations

from PIL import Image
from PyQt6.QtGui import QImage, QPixmap


def pil_to_qimage(image: Image.Image) -> QImage:
    if image.mode not in ("RGBA", "RGB"):
        image = image.convert("RGBA" if "A" in image.mode else "RGB")
    data = image.tobytes("raw", image.mode)
    fmt = QImage.Format.Format_RGBA8888 if image.mode == "RGBA" else QImage.Format.Format_RGB888
    qimg = QImage(data, image.width, image.height, fmt)
    # Copy so the QImage owns its buffer independent of Pillow's memory.
    return qimg.copy()


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    return QPixmap.fromImage(pil_to_qimage(image))


def make_thumbnail_pixmap(image: Image.Image, size: int) -> QPixmap:
    thumb = image.copy()
    thumb.thumbnail((size, size), Image.Resampling.LANCZOS)
    pix = pil_to_qpixmap(thumb)
    return pix
