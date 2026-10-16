"""Background execution of the Auto-Stack (feature-matching) photo stitch.

Decoding and downscaling dozens of full-resolution photos one by one can
itself take a noticeable moment, so that part reports per-file progress;
OpenCV's actual alignment/blending pass is a single call with no progress of
its own, so the dialog just shows a busy indicator for that part.
"""
from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from ..core import image_ops
from ..core.autostack_ops import AutoStackError, AutoStackOptions, downscale_for_stitch, stitch


class AutoStackWorker(QThread):
    loadProgress = pyqtSignal(int, int, str)  # done, total, path
    stitchingStarted = pyqtSignal()
    finishedStack = pyqtSignal(object)  # AutoStackResult
    failed = pyqtSignal(str)

    def __init__(self, paths: list[str], options: AutoStackOptions, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.options = options

    def run(self) -> None:
        images: list[Image.Image] = []
        total = len(self.paths)
        try:
            for i, path in enumerate(self.paths):
                if self.isInterruptionRequested():
                    return
                image = image_ops.load_with_orientation(path)
                images.append(downscale_for_stitch(image, self.options.max_working_dim))
                self.loadProgress.emit(i + 1, total, path)

            if self.isInterruptionRequested():
                return

            self.stitchingStarted.emit()
            result = stitch(images, self.options)
        except AutoStackError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not a crash
            self.failed.emit(f"Unexpected error: {exc}")
            return
        self.finishedStack.emit(result)
