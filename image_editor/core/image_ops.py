"""Pure image editing operations built on Pillow.

Every function takes a PIL.Image.Image and returns a new one; nothing here
mutates its input, so the caller stays free to keep the original around for
undo/redo or a "revert" action.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


def rotate90(image: Image.Image, clockwise: bool = True) -> Image.Image:
    """Losslessly rotate by 90 degrees."""
    return image.transpose(
        Image.Transpose.ROTATE_270 if clockwise else Image.Transpose.ROTATE_90
    )


def rotate180(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.ROTATE_180)


def rotate_arbitrary(image: Image.Image, degrees: float, expand: bool = True) -> Image.Image:
    """Rotate by an arbitrary angle (counter-clockwise, degrees)."""
    fill = (0, 0, 0, 0) if image.mode == "RGBA" else (0, 0, 0)
    return image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=expand, fillcolor=fill)


def flip_horizontal(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)


def flip_vertical(image: Image.Image) -> Image.Image:
    return image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def crop(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    """Crop to ``box`` = (left, top, right, bottom) in pixel coordinates."""
    left, top, right, bottom = box
    left = max(0, min(left, image.width - 1))
    top = max(0, min(top, image.height - 1))
    right = max(left + 1, min(right, image.width))
    bottom = max(top + 1, min(bottom, image.height))
    return image.crop((left, top, right, bottom))


def perspective_crop(
    image: Image.Image, corners: tuple[tuple[float, float], ...]
) -> Image.Image:
    """Crop an asymmetric quadrilateral and unwarp it into a rectangle.

    ``corners`` are four (x, y) pixel coordinates in the order
    top-left, top-right, bottom-right, bottom-left. Unlike a plain
    rectangular crop, the four corners need not form a rectangle - this
    is meant for straightening a document or sign photographed from an
    angle, where each side of the subject has a different length and
    skew in the source photo.

    The output size is derived from the quad's own edge lengths (the
    longer of each opposing pair), so the result keeps roughly the
    subject's real proportions instead of being forced into the
    original photo's aspect ratio.
    """
    tl, tr, br, bl = (np.array(pt, dtype=np.float32) for pt in corners)
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    width = max(1, round(width))
    height = max(1, round(height))

    src = np.array([tl, tr, br, bl], dtype=np.float32)
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)

    has_alpha = image.mode in ("RGBA", "LA")
    source = np.array(image.convert("RGBA") if has_alpha else image.convert("RGB"))
    warped = cv2.warpPerspective(
        source,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0) if has_alpha else (0, 0, 0),
    )
    result = Image.fromarray(warped, "RGBA" if has_alpha else "RGB")
    return result if result.mode == image.mode else result.convert(image.mode)


def resize(image: Image.Image, size: tuple[int, int], keep_aspect: bool = True) -> Image.Image:
    """Resize exactly to ``size`` or fit within it while preserving aspect ratio."""
    if keep_aspect:
        result = image.copy()
        result.thumbnail(size, Image.Resampling.LANCZOS)
        return result
    return image.resize(size, Image.Resampling.LANCZOS)


def _factor_from_slider(value: float) -> float:
    """Map a -100..100 slider value to a Pillow enhancement factor (0..2)."""
    value = max(-100.0, min(100.0, value))
    return 1.0 + (value / 100.0)


def apply_brightness(image: Image.Image, value: float) -> Image.Image:
    if value == 0:
        return image
    return ImageEnhance.Brightness(image).enhance(_factor_from_slider(value))


def apply_contrast(image: Image.Image, value: float) -> Image.Image:
    if value == 0:
        return image
    return ImageEnhance.Contrast(image).enhance(_factor_from_slider(value))


def apply_saturation(image: Image.Image, value: float) -> Image.Image:
    if value == 0:
        return image
    return ImageEnhance.Color(image).enhance(_factor_from_slider(value))


def apply_rgb_channels(image: Image.Image, r: float, g: float, b: float) -> Image.Image:
    """Scale each RGB channel independently. Values are -100..100 (percent)."""
    if r == 0 and g == 0 and b == 0:
        return image

    has_alpha = image.mode in ("RGBA", "LA")
    base = image.convert("RGBA") if has_alpha else image.convert("RGB")
    bands = list(base.split())
    factors = (_factor_from_slider(r), _factor_from_slider(g), _factor_from_slider(b))
    for i, factor in enumerate(factors):
        if factor == 1.0:
            continue
        lut = [min(255, max(0, round(x * factor))) for x in range(256)]
        bands[i] = bands[i].point(lut)
    result = Image.merge(base.mode, bands)
    return result.convert(image.mode) if result.mode != image.mode else result


def apply_adjustments(
    image: Image.Image,
    *,
    brightness: float = 0,
    contrast: float = 0,
    saturation: float = 0,
    red: float = 0,
    green: float = 0,
    blue: float = 0,
) -> Image.Image:
    """Apply percentage adjustments in brightness, contrast, saturation, RGB order.

    Each adjustment value is clamped to the range -100 through 100.
    """
    result = image
    result = apply_brightness(result, brightness)
    result = apply_contrast(result, contrast)
    result = apply_saturation(result, saturation)
    result = apply_rgb_channels(result, red, green, blue)
    return result


def autocontrast(image: Image.Image, cutoff: float = 0.5) -> Image.Image:
    """Apply automatic contrast while preserving an RGBA image's alpha channel."""
    if image.mode == "RGBA":
        rgb, alpha = image.convert("RGB"), image.getchannel("A")
        adjusted = ImageOps.autocontrast(rgb, cutoff=cutoff)
        adjusted.putalpha(alpha)
        return adjusted
    return ImageOps.autocontrast(image.convert("RGB"), cutoff=cutoff)


def grayscale(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return gray.convert(image.mode) if image.mode in ("RGBA",) else gray


# Pixel-geometry EXIF tags that describe the *encoded* bitmap. After rotate,
# crop or resize they no longer match the pixels and must be rewritten.
_TAG_ORIENTATION = 0x0112
_TAG_IMAGE_WIDTH = 0x0100
_TAG_IMAGE_LENGTH = 0x0101
_IFD_EXIF = 0x8769
_TAG_PIXEL_X_DIMENSION = 0xA002
_TAG_PIXEL_Y_DIMENSION = 0xA003

# Formats whose Pillow encoders accept ``exif=`` and ``icc_profile=``.
METADATA_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"})


@dataclass(frozen=True)
class ImageMetadata:
    """EXIF block and ICC profile carried over from a source file.

    ``icc_profile`` is only captured for RGB/RGBA sources. The editor decodes
    other modes (CMYK, grayscale, palette) to RGB without colour management,
    so tagging that RGB output with the source profile would shift colours.
    """

    exif: bytes | None = None
    icc_profile: bytes | None = None


def capture_metadata(image: Image.Image) -> ImageMetadata:
    """Read EXIF and ICC from ``image``. Call before any mode conversion."""
    exif = image.info.get("exif") or None
    icc = image.info.get("icc_profile") or None
    if image.mode not in ("RGB", "RGBA"):
        icc = None
    return ImageMetadata(exif=exif, icc_profile=icc)


def load_oriented_with_metadata(path: str | Path) -> tuple[Image.Image, ImageMetadata]:
    """Open an image with EXIF orientation baked in, plus its metadata."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img.load()
    return img, capture_metadata(img)


def load_with_orientation(path: str) -> Image.Image:
    """Open an image and bake any EXIF orientation into the pixel data."""
    return load_oriented_with_metadata(path)[0]


def _output_exif(exif_bytes: bytes | None, size: tuple[int, int]) -> bytes:
    """Return EXIF for an output bitmap of ``size``, or ``b""`` to omit it.

    The orientation is reset to 1 because the pixels are already upright, and
    the pixel-dimension tags are rewritten to the output size so they do not
    describe the pre-edit bitmap.
    """
    if not exif_bytes:
        return b""
    exif = Image.Exif()
    try:
        exif.load(exif_bytes)
    except Exception:  # noqa: BLE001 - an unparseable block is dropped, not fatal
        return b""
    width, height = size
    exif[_TAG_ORIENTATION] = 1
    if _TAG_IMAGE_WIDTH in exif:
        exif[_TAG_IMAGE_WIDTH] = width
    if _TAG_IMAGE_LENGTH in exif:
        exif[_TAG_IMAGE_LENGTH] = height
    if _IFD_EXIF in exif:
        sub = exif.get_ifd(_IFD_EXIF)
        if _TAG_PIXEL_X_DIMENSION in sub:
            sub[_TAG_PIXEL_X_DIMENSION] = width
        if _TAG_PIXEL_Y_DIMENSION in sub:
            sub[_TAG_PIXEL_Y_DIMENSION] = height
    return exif.tobytes()


def metadata_save_kwargs(
    metadata: ImageMetadata | None,
    extension: str,
    size: tuple[int, int],
) -> dict:
    """Pillow ``save()`` kwargs that carry ``metadata`` into an output file.

    Passing ``metadata=None`` still returns explicit empty values for formats
    that support metadata. PNG and TIFF otherwise copy ``im.info["icc_profile"]``
    automatically, so omitting the kwarg would not strip the profile.
    """
    if extension.lower() not in METADATA_EXTENSIONS:
        return {}
    if metadata is None:
        return {"exif": b"", "icc_profile": None}
    return {
        "exif": _output_exif(metadata.exif, size),
        "icc_profile": metadata.icc_profile,
    }


def load_thumbnail(path: str, size: int) -> Image.Image:
    """Open an image already downscaled to roughly ``size``, oriented upright.

    Decoding a multi-megapixel photo at full resolution just to shrink it to
    a thumbnail wastes most of the work: for JPEGs, ``Image.draft`` asks the
    decoder itself to hand back a smaller image (using cheap DCT downscaling),
    so ``img.load()`` below never materializes the full-size pixel buffer.
    Other formats ignore draft and still load at full size, but JPEG is the
    overwhelming majority of photos in a typical folder, so this still turns
    "decode everything in Downloads" from a multi-second-per-file cost into
    a near-instant one.
    """
    img = Image.open(path)
    img.draft("RGB", (size, size))
    img = ImageOps.exif_transpose(img)
    img.load()
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    return img
