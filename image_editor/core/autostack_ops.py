"""Feature-based "smart stacking": combine many overlapping photos of the
same flat scene (e.g. dozens of garden shots taken from above) into one
large image, by matching visual patterns between photos instead of placing
them on a fixed layout (see core/stitch_ops.py for that simpler tool).

Built on OpenCV's Stitcher, which does the feature detection, matching,
alignment and blending; this module adapts it to PIL images, turns its
failure codes into messages a user can act on, and - critically - uses its
two-step API (estimateTransform + composePanorama) instead of the one-shot
stitch(). The one-shot call will happily return status OK while silently
leaving out any photo it couldn't confidently chain to the rest (e.g. most
of a large, not-strictly-sequential batch), with nothing in the return
value to say so. The two-step API exposes stitcher.component(): the indices
of the photos actually used, so callers can tell the user when their batch
only partially stitched instead of quietly handing back a tiny result.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

MODE_FLAT = "flat"
MODE_PANORAMA = "panorama"
MODE_AUTO = "auto"
STITCH_MODES = (MODE_AUTO, MODE_FLAT, MODE_PANORAMA)

_CV_MODE = {
    MODE_FLAT: cv2.Stitcher_SCANS,
    MODE_PANORAMA: cv2.Stitcher_PANORAMA,
}
# Auto tries every real mode and keeps whichever manages to chain together
# the most photos - neither mode is reliably better for an arbitrary batch
# (SCANS assumes a fairly direct scan/grid pattern; PANORAMA does full
# bundle adjustment and tends to cope better with photos taken by walking
# around in no particular order, but not always).
_AUTO_CANDIDATES = (MODE_FLAT, MODE_PANORAMA)

_STATUS_MESSAGES = {
    cv2.Stitcher_ERR_NEED_MORE_IMGS: (
        "Not enough matching detail was found between the photos. Make sure "
        "consecutive photos overlap by at least 30-50% and show real texture "
        "(not a plain lawn/sky with nothing to match)."
    ),
    cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: (
        "Could not line up the photos geometrically. Try the other mode, or "
        "drop photos that barely overlap with their neighbours."
    ),
    cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: (
        "Could not reconcile all the photos into a single consistent result."
    ),
}


@dataclass
class AutoStackOptions:
    mode: str = MODE_AUTO
    max_working_dim: int = 2000  # 0 = use full resolution


@dataclass
class AutoStackResult:
    image: Image.Image
    mode_used: str
    used_indices: list[int]
    total_count: int

    @property
    def used_count(self) -> int:
        return len(self.used_indices)

    @property
    def dropped_count(self) -> int:
        return self.total_count - self.used_count


class AutoStackError(Exception):
    """Raised when the photos could not be combined; message is user-facing."""


def _pil_to_cv(image: Image.Image) -> np.ndarray:
    arr = np.array(image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _cv_to_pil(mat: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(mat, cv2.COLOR_BGR2RGB))


def downscale_for_stitch(image: Image.Image, max_dim: int) -> Image.Image:
    """Shrink ``image`` so its longest side is at most ``max_dim`` (0 = no cap).

    Exposed so callers that decode photos one at a time (to report per-file
    progress) can downscale right after loading, instead of holding dozens of
    full-resolution photos in memory until :func:`stitch` runs.
    """
    if max_dim <= 0 or max(image.size) <= max_dim:
        return image
    scaled = image.copy()
    scaled.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return scaled


def _try_estimate(mode: str, prepared: list[np.ndarray]):
    """Run estimateTransform() for one mode. Returns (stitcher, indices) on
    success, or (None, status) on failure."""
    stitcher = cv2.Stitcher_create(_CV_MODE[mode])
    status = stitcher.estimateTransform(prepared)
    if status != cv2.Stitcher_OK:
        return None, status
    return stitcher, stitcher.component()


def stitch(images: list[Image.Image], options: AutoStackOptions) -> AutoStackResult:
    """Combine overlapping photos into one image by matching visual features.

    The result reports which of the input photos actually made it into the
    final image (``used_indices``/``used_count``/``dropped_count``) - the
    underlying stitcher can and does leave photos out when it can't chain
    them to the rest with enough confidence, without that being an error.

    Raises AutoStackError (with a message safe to show the user) if no mode
    could align/blend anything at all.
    """
    if len(images) < 2:
        raise AutoStackError("Add at least two overlapping photos.")

    prepared = [_pil_to_cv(downscale_for_stitch(img, options.max_working_dim)) for img in images]

    candidates = _AUTO_CANDIDATES if options.mode == MODE_AUTO else (options.mode,)

    best: tuple[object, str, object] | None = None  # (stitcher, mode, indices)
    last_status = None
    for mode in candidates:
        stitcher, outcome = _try_estimate(mode, prepared)
        if stitcher is None:
            last_status = outcome
            continue
        indices = outcome
        if best is None or len(indices) > len(best[2]):
            best = (stitcher, mode, indices)
        if len(indices) == len(images):
            break  # already used every photo - no point trying another mode

    if best is None:
        message = _STATUS_MESSAGES.get(last_status, f"Stitching failed (OpenCV status {last_status}).")
        raise AutoStackError(message)

    stitcher, mode_used, indices = best
    status, pano = stitcher.composePanorama()
    if status != cv2.Stitcher_OK:
        message = _STATUS_MESSAGES.get(status, f"Stitching failed while blending (OpenCV status {status}).")
        raise AutoStackError(message)

    return AutoStackResult(
        image=_cv_to_pil(pano),
        mode_used=mode_used,
        used_indices=sorted(int(i) for i in indices),
        total_count=len(images),
    )
