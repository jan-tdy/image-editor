"""Feature-based "smart stacking": combine many overlapping photos of the
same flat scene (e.g. dozens of garden shots taken from above) into one
large image, by matching visual patterns between photos instead of placing
them on a fixed layout (see core/stitch_ops.py for that simpler tool).

Built on OpenCV's Stitcher, which does the feature detection, matching,
alignment and blending; this module just adapts it to PIL images and turns
its failure codes into messages a user can act on.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

MODE_FLAT = "flat"
MODE_PANORAMA = "panorama"
STITCH_MODES = (MODE_FLAT, MODE_PANORAMA)

_CV_MODE = {
    MODE_FLAT: cv2.Stitcher_SCANS,
    MODE_PANORAMA: cv2.Stitcher_PANORAMA,
}

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
    mode: str = MODE_FLAT
    max_working_dim: int = 2000  # 0 = use full resolution


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


def stitch(images: list[Image.Image], options: AutoStackOptions) -> Image.Image:
    """Combine overlapping photos into one image by matching visual features.

    Raises AutoStackError (with a message safe to show the user) if the
    photos could not be aligned/blended.
    """
    if len(images) < 2:
        raise AutoStackError("Add at least two overlapping photos.")

    prepared = [_pil_to_cv(downscale_for_stitch(img, options.max_working_dim)) for img in images]

    stitcher = cv2.Stitcher_create(_CV_MODE.get(options.mode, cv2.Stitcher_SCANS))
    status, result = stitcher.stitch(prepared)

    if status != cv2.Stitcher_OK:
        message = _STATUS_MESSAGES.get(status, f"Stitching failed (OpenCV status {status}).")
        raise AutoStackError(message)

    return _cv_to_pil(result)
