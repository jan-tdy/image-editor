"""In-memory editable representation of one open image.

An ImageDocument keeps a "baked" base image (the result of all committed
geometric edits: rotate/flip/crop) plus a set of live, non-destructive
adjustment values (brightness/contrast/saturation/RGB) that are re-applied
on top of the base image for preview and are only baked in when explicitly
committed. This keeps slider dragging fast (no undo-stack spam) while still
giving rotate/crop/flip/apply-adjustments their own undo steps.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

from . import image_ops

MAX_UNDO_DEPTH = 25


@dataclass(frozen=True)
class Adjustments:
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    red: float = 0.0
    green: float = 0.0
    blue: float = 0.0

    def is_identity(self) -> bool:
        return self == Adjustments()


class ImageDocument:
    def __init__(self, path: str | None = None):
        self.path: str | None = None
        self.original: Image.Image | None = None
        self.base_image: Image.Image | None = None
        self.adjustments = Adjustments()

        self._undo_stack: list[Image.Image] = []
        self._redo_stack: list[Image.Image] = []
        self._preview_cache: Image.Image | None = None
        self._preview_cache_key: Adjustments | None = None
        self.dirty = False

        if path:
            self.load(path)

    # -- loading / saving -------------------------------------------------
    def load(self, path: str) -> None:
        image = image_ops.load_with_orientation(path)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("P", "LA") else "RGB")
        self.path = str(path)
        self.original = image
        self.base_image = image.copy()
        self.adjustments = Adjustments()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._invalidate_preview()
        self.dirty = False

    def save(self, path: str | None = None, quality: int = 95) -> str:
        if self.base_image is None:
            raise RuntimeError("No image loaded")
        target = path or self.path
        if not target:
            raise ValueError("No destination path given")
        image = self.preview_image()
        ext = Path(target).suffix.lower()
        save_kwargs = {}
        if ext in (".jpg", ".jpeg"):
            image = image.convert("RGB")
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        elif ext == ".png":
            save_kwargs["optimize"] = True
        image.save(target, **save_kwargs)
        self.path = target
        self.dirty = False
        return target

    # -- preview ------------------------------------------------------------
    def preview_image(self) -> Image.Image:
        if self.base_image is None:
            raise RuntimeError("No image loaded")
        if self.adjustments.is_identity():
            return self.base_image
        if self._preview_cache is not None and self._preview_cache_key == self.adjustments:
            return self._preview_cache
        result = image_ops.apply_adjustments(
            self.base_image,
            brightness=self.adjustments.brightness,
            contrast=self.adjustments.contrast,
            saturation=self.adjustments.saturation,
            red=self.adjustments.red,
            green=self.adjustments.green,
            blue=self.adjustments.blue,
        )
        self._preview_cache = result
        self._preview_cache_key = self.adjustments
        return result

    def _invalidate_preview(self) -> None:
        self._preview_cache = None
        self._preview_cache_key = None

    # -- adjustments (non-destructive, live) --------------------------------
    def set_adjustments(self, **kwargs) -> None:
        self.adjustments = replace(self.adjustments, **kwargs)
        self._invalidate_preview()
        self.dirty = True

    def reset_adjustments(self) -> None:
        self.adjustments = Adjustments()
        self._invalidate_preview()

    def commit_adjustments(self) -> bool:
        """Bake current adjustment values into base_image as an undo step."""
        if self.adjustments.is_identity():
            return False
        self._push_undo()
        self.base_image = self.preview_image()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    # -- geometric edits (each is its own undo step) -------------------------
    def _push_undo(self) -> None:
        assert self.base_image is not None
        self._undo_stack.append(self.base_image.copy())
        if len(self._undo_stack) > MAX_UNDO_DEPTH:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _apply_geometry(self, fn) -> None:
        if self.base_image is None:
            return
        self.commit_adjustments()
        self._push_undo()
        self.base_image = fn(self.base_image)
        self._invalidate_preview()
        self.dirty = True

    def rotate90(self, clockwise: bool = True) -> None:
        self._apply_geometry(lambda img: image_ops.rotate90(img, clockwise))

    def rotate_arbitrary(self, degrees: float) -> None:
        self._apply_geometry(lambda img: image_ops.rotate_arbitrary(img, degrees))

    def flip_horizontal(self) -> None:
        self._apply_geometry(image_ops.flip_horizontal)

    def flip_vertical(self) -> None:
        self._apply_geometry(image_ops.flip_vertical)

    def crop(self, box: tuple[int, int, int, int]) -> None:
        self._apply_geometry(lambda img: image_ops.crop(img, box))

    # -- undo / redo ----------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        if not self._undo_stack or self.base_image is None:
            return False
        self._redo_stack.append(self.base_image.copy())
        self.base_image = self._undo_stack.pop()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack or self.base_image is None:
            return False
        self._undo_stack.append(self.base_image.copy())
        self.base_image = self._redo_stack.pop()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    def revert_to_original(self) -> None:
        if self.original is None:
            return
        self._push_undo()
        self.base_image = self.original.copy()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True

    @property
    def size(self) -> tuple[int, int]:
        if self.base_image is None:
            return (0, 0)
        return self.base_image.size
