"""Pure image editing operations built on Pillow.

Every function takes a PIL.Image.Image and returns a new one; nothing here
mutates its input, so the caller stays free to keep the original around for
undo/redo or a "revert" action.
"""
from __future__ import annotations

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


def resize(image: Image.Image, size: tuple[int, int], keep_aspect: bool = True) -> Image.Image:
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
    """Apply the full adjustment chain in one predictable order."""
    result = image
    result = apply_brightness(result, brightness)
    result = apply_contrast(result, contrast)
    result = apply_saturation(result, saturation)
    result = apply_rgb_channels(result, red, green, blue)
    return result


def autocontrast(image: Image.Image, cutoff: float = 0.5) -> Image.Image:
    if image.mode == "RGBA":
        rgb, alpha = image.convert("RGB"), image.getchannel("A")
        adjusted = ImageOps.autocontrast(rgb, cutoff=cutoff)
        adjusted.putalpha(alpha)
        return adjusted
    return ImageOps.autocontrast(image.convert("RGB"), cutoff=cutoff)


def grayscale(image: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(image)
    return gray.convert(image.mode) if image.mode in ("RGBA",) else gray


def load_with_orientation(path: str) -> Image.Image:
    """Open an image and bake any EXIF orientation into the pixel data."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img.load()
    return img
