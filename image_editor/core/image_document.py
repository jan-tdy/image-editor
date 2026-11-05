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

from PIL import Image, ImageSequence

from . import image_ops

MAX_UNDO_DEPTH = 25
# Upper bound on the pixel data kept for undo + redo combined. A 50 MP RGBA
# photo is ~200 MB per step, so a count-only limit could reach several GB.
# The newest undo step is always kept, even if it alone exceeds the budget.
MAX_UNDO_BYTES = 512 * 1024 * 1024
DEFAULT_FRAME_DURATION_MS = 100

# Approximate bytes per pixel for the modes the editor can hold.
_BYTES_PER_PIXEL = {
    "1": 1, "L": 1, "P": 1,
    "LA": 2, "PA": 2, "I;16": 2, "I;16L": 2, "I;16B": 2,
    "RGB": 3, "YCbCr": 3, "LAB": 3, "HSV": 3,
    "RGBA": 4, "RGBX": 4, "RGBa": 4, "CMYK": 4, "I": 4, "F": 4,
}


def _image_nbytes(image: Image.Image) -> int:
    return image.width * image.height * _BYTES_PER_PIXEL.get(image.mode, 4)


def _snapshot_nbytes(snapshot: Image.Image | list[Image.Image]) -> int:
    if isinstance(snapshot, list):
        return sum(_image_nbytes(frame) for frame in snapshot)
    return _image_nbytes(snapshot)


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
        # EXIF/ICC from the source file, and whether save() carries them over.
        self.metadata = image_ops.ImageMetadata()
        self.keep_metadata = True
        self.undo_budget_bytes = MAX_UNDO_BYTES

        # Animated-GIF state. ``frames`` is None for an ordinary still image;
        # when set, it holds every frame (each the same size as base_image)
        # and base_image always mirrors frames[current_frame_index], so every
        # existing single-image code path (preview_image, size, ...) keeps
        # working unchanged against "the currently displayed frame".
        self.frames: list[Image.Image] | None = None
        self.original_frames: list[Image.Image] | None = None
        self.frame_durations: list[int] = []
        self.frame_disposal: list[int] = []
        self.loop_count = 0
        self.current_frame_index = 0

        self._undo_stack: list[Image.Image | list[Image.Image]] = []
        self._redo_stack: list[Image.Image | list[Image.Image]] = []
        self._preview_cache: Image.Image | None = None
        self._preview_cache_key: Adjustments | None = None
        self.dirty = False

        if path:
            self.load(path)

    @property
    def is_animated(self) -> bool:
        return bool(self.frames and len(self.frames) > 1)

    @property
    def frame_count(self) -> int:
        return len(self.frames) if self.frames else 1

    # -- loading / saving -------------------------------------------------
    def load(self, path: str) -> None:
        """Load an image with EXIF orientation applied and reset all edit state."""
        raw = Image.open(path)
        if getattr(raw, "is_animated", False) and getattr(raw, "n_frames", 1) > 1:
            self._load_animated(raw, path)
            return

        image, self.metadata = image_ops.load_oriented_with_metadata(path)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info or image.mode in ("P", "LA") else "RGB")
        self.path = str(path)
        # Loaded images are never mutated in place (every edit builds a new
        # image), so original and base_image can share one object.
        self.original = image
        self.base_image = image
        self.frames = None
        self.original_frames = None
        self.frame_durations = []
        self.frame_disposal = []
        self.loop_count = 0
        self.current_frame_index = 0
        self.adjustments = Adjustments()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._invalidate_preview()
        self.dirty = False

    def _load_animated(self, raw: Image.Image, path: str) -> None:
        """Load every frame of an animated GIF (or other multi-frame format
        Pillow reports as animated), keeping each frame's duration/disposal
        so :meth:`save` can round-trip the animation."""
        frames: list[Image.Image] = []
        durations: list[int] = []
        disposals: list[int] = []
        for frame in ImageSequence.Iterator(raw):
            frames.append(frame.convert("RGBA"))
            durations.append(frame.info.get("duration") or DEFAULT_FRAME_DURATION_MS)
            disposals.append(getattr(frame, "disposal_method", 2))

        self.path = str(path)
        self.metadata = image_ops.ImageMetadata()
        self.frames = frames
        self.original_frames = list(frames)
        self.frame_durations = durations
        self.frame_disposal = disposals
        self.loop_count = raw.info.get("loop", 0)
        self.current_frame_index = 0
        self.original = frames[0]
        self.base_image = frames[0]
        self.adjustments = Adjustments()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._invalidate_preview()
        self.dirty = False

    def set_current_frame(self, index: int) -> None:
        """Switch the displayed/editable frame of an animated document.

        Bakes any pending live adjustments into the frame being left first,
        same as switching away via a geometric edit would.
        """
        if not self.frames:
            return
        index = max(0, min(index, len(self.frames) - 1))
        if index == self.current_frame_index:
            return
        self.commit_adjustments()
        self.current_frame_index = index
        self.base_image = self.frames[index]
        self._invalidate_preview()

    def save(self, path: str | None = None, quality: int = 95) -> str:
        """Bake pending adjustments, save the image, and mark the document clean.

        Raises ``RuntimeError`` if no image is loaded and ``ValueError`` if no
        destination is available. Returns the destination path.
        """
        if self.base_image is None:
            raise RuntimeError("No image loaded")
        target = path or self.path
        if not target:
            raise ValueError("No destination path given")
        # Bake any live (uncommitted) adjustments into base_image first, so
        # the in-memory state matches exactly what's written to disk. Saving
        # preview_image() without this leaves base_image stale: resetting
        # adjustments afterwards (e.g. closing the panel) would silently
        # diverge the displayed image from the saved file while `dirty`
        # still read False.
        self.commit_adjustments()
        ext = Path(target).suffix.lower()

        if self.is_animated and ext == ".gif":
            self.frames[0].save(
                target,
                format="GIF",
                save_all=True,
                append_images=self.frames[1:],
                duration=self.frame_durations,
                disposal=self.frame_disposal,
                loop=self.loop_count,
            )
            self.path = target
            self.dirty = False
            return target

        # Either a still image, or exporting one frame of an animated
        # document to a non-animated format - only the currently displayed
        # frame is written in that case.
        image = self.preview_image()
        save_kwargs = {}
        if ext in (".jpg", ".jpeg"):
            image = image.convert("RGB")
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        elif ext == ".png":
            save_kwargs["optimize"] = True
        save_kwargs.update(
            image_ops.metadata_save_kwargs(
                self.metadata if self.keep_metadata else None, ext, image.size
            )
        )
        image.save(target, **save_kwargs)
        self.path = target
        self.dirty = False
        return target

    # -- preview ------------------------------------------------------------
    def preview_image(self) -> Image.Image:
        """Return the baked image with live adjustments applied.

        Raises ``RuntimeError`` if no image is loaded.
        """
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
        """Update named live adjustments and mark the document as modified."""
        self.adjustments = replace(self.adjustments, **kwargs)
        self._invalidate_preview()
        self.dirty = True

    def reset_adjustments(self) -> None:
        """Clear live adjustments without changing the baked image."""
        self.adjustments = Adjustments()
        self._invalidate_preview()

    def commit_adjustments(self) -> bool:
        """Bake live adjustments as an undo step and report whether any were set."""
        if self.adjustments.is_identity():
            return False
        self._push_undo()
        if self.is_animated:
            # Adjustments are previewed live on just the current frame (cheap,
            # for smooth slider dragging) but baked into every frame on
            # commit, so the exported animation stays consistent across frames.
            self.frames = [
                image_ops.apply_adjustments(
                    frame,
                    brightness=self.adjustments.brightness,
                    contrast=self.adjustments.contrast,
                    saturation=self.adjustments.saturation,
                    red=self.adjustments.red,
                    green=self.adjustments.green,
                    blue=self.adjustments.blue,
                )
                for frame in self.frames
            ]
            self.base_image = self.frames[self.current_frame_index]
        else:
            self.base_image = self.preview_image()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    # -- geometric edits (each is its own undo step) -------------------------
    # Snapshots hold references, not copies. This is safe because every edit
    # assigns a freshly built image (or frame list) and never mutates the
    # current one, so a stored snapshot cannot change underneath the history.
    def _snapshot(self) -> Image.Image | list[Image.Image]:
        if self.is_animated:
            return list(self.frames)
        return self.base_image

    def _restore(self, snapshot: Image.Image | list[Image.Image]) -> None:
        if isinstance(snapshot, list):
            self.frames = snapshot
            self.current_frame_index = min(self.current_frame_index, len(self.frames) - 1)
            self.base_image = self.frames[self.current_frame_index]
        else:
            self.base_image = snapshot

    def _history_nbytes(self) -> int:
        return sum(_snapshot_nbytes(s) for s in self._undo_stack) + sum(
            _snapshot_nbytes(s) for s in self._redo_stack
        )

    def _enforce_history_budget(self) -> None:
        """Drop the oldest history entries until count and byte limits hold.

        Undo entries are evicted before redo entries, and the newest undo
        entry is never evicted, so a single step of undo always remains.
        """
        for stack in (self._undo_stack, self._redo_stack):
            while len(stack) > MAX_UNDO_DEPTH:
                stack.pop(0)
        while self._history_nbytes() > self.undo_budget_bytes:
            if len(self._undo_stack) > 1:
                self._undo_stack.pop(0)
            elif len(self._redo_stack) > 1:
                self._redo_stack.pop(0)
            else:
                break

    def _push_undo(self) -> None:
        assert self.base_image is not None
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()
        self._enforce_history_budget()

    def _apply_geometry(self, fn) -> None:
        if self.base_image is None:
            return
        self.commit_adjustments()
        self._push_undo()
        if self.is_animated:
            # Geometric edits apply to every frame so the whole animation
            # stays in sync (e.g. rotating a GIF rotates all of it, not just
            # whichever frame happened to be on screen).
            self.frames = [fn(frame) for frame in self.frames]
            self.base_image = self.frames[self.current_frame_index]
        else:
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

    def auto_adjust(self) -> None:
        """One-click auto contrast/levels, baked in as its own undo step."""
        self._apply_geometry(image_ops.autocontrast)

    # -- undo / redo ----------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> bool:
        """Restore the previous baked image and report whether one existed."""
        if not self._undo_stack or self.base_image is None:
            return False
        self._redo_stack.append(self._snapshot())
        self._restore(self._undo_stack.pop())
        self._enforce_history_budget()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    def redo(self) -> bool:
        """Restore the next baked image and report whether one existed."""
        if not self._redo_stack or self.base_image is None:
            return False
        self._undo_stack.append(self._snapshot())
        self._restore(self._redo_stack.pop())
        self._enforce_history_budget()
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True
        return True

    def revert_to_original(self) -> None:
        """Restore the originally loaded image as an undoable edit, if present."""
        if self.original is None:
            return
        self._push_undo()
        if self.original_frames is not None:
            self.frames = list(self.original_frames)
            self.current_frame_index = min(self.current_frame_index, len(self.frames) - 1)
            self.base_image = self.frames[self.current_frame_index]
        else:
            self.base_image = self.original
        self.adjustments = Adjustments()
        self._invalidate_preview()
        self.dirty = True

    @property
    def size(self) -> tuple[int, int]:
        if self.base_image is None:
            return (0, 0)
        return self.base_image.size
