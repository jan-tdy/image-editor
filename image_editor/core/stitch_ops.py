"""Compose several images side by side: horizontal, vertical or grid layout."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

RGBA = tuple[int, int, int, int]

DIRECTIONS = ("horizontal", "vertical", "grid")
RESIZE_MODES = ("none", "match_smallest", "match_largest", "custom")
H_ALIGNMENTS = ("top", "center", "bottom")
V_ALIGNMENTS = ("left", "center", "right")


@dataclass
class StitchOptions:
    direction: str = "horizontal"
    spacing: int = 10
    background: RGBA = (255, 255, 255, 255)
    align: str = "center"
    columns: int = 3
    resize_mode: str = "none"
    custom_size: int = 512


def _scale_to(image: Image.Image, target: int, axis: str) -> Image.Image:
    if axis == "height":
        if image.height == target:
            return image
        ratio = target / image.height
        new_size = (max(1, round(image.width * ratio)), max(1, target))
    else:
        if image.width == target:
            return image
        ratio = target / image.width
        new_size = (max(1, target), max(1, round(image.height * ratio)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _fit_within(image: Image.Image, box_w: int, box_h: int) -> Image.Image:
    if image.width <= box_w and image.height <= box_h:
        return image
    result = image.copy()
    result.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)
    return result


def _align_offset(align: str, total: int, size: int) -> int:
    if align in ("top", "left"):
        return 0
    if align in ("bottom", "right"):
        return total - size
    return (total - size) // 2


def _normalized(images: list[Image.Image], axis: str, options: StitchOptions) -> list[Image.Image]:
    if options.resize_mode == "none":
        return images
    sizes = [img.height if axis == "height" else img.width for img in images]
    if options.resize_mode == "match_smallest":
        target = min(sizes)
    elif options.resize_mode == "match_largest":
        target = max(sizes)
    else:
        target = max(1, options.custom_size)
    return [_scale_to(img, target, axis) for img in images]


def compose_horizontal(images: list[Image.Image], options: StitchOptions) -> Image.Image:
    images = _normalized(images, "height", options)
    spacing = max(0, options.spacing)
    total_w = sum(img.width for img in images) + spacing * (len(images) - 1)
    total_h = max(img.height for img in images)
    canvas = Image.new("RGBA", (max(1, total_w), max(1, total_h)), options.background)
    x = 0
    for img in images:
        rgba = img.convert("RGBA")
        y = _align_offset(options.align, total_h, rgba.height)
        canvas.paste(rgba, (x, y), rgba)
        x += rgba.width + spacing
    return canvas


def compose_vertical(images: list[Image.Image], options: StitchOptions) -> Image.Image:
    images = _normalized(images, "width", options)
    spacing = max(0, options.spacing)
    total_w = max(img.width for img in images)
    total_h = sum(img.height for img in images) + spacing * (len(images) - 1)
    canvas = Image.new("RGBA", (max(1, total_w), max(1, total_h)), options.background)
    y = 0
    for img in images:
        rgba = img.convert("RGBA")
        x = _align_offset(options.align, total_w, rgba.width)
        canvas.paste(rgba, (x, y), rgba)
        y += rgba.height + spacing
    return canvas


def compose_grid(images: list[Image.Image], options: StitchOptions) -> Image.Image:
    spacing = max(0, options.spacing)
    columns = max(1, options.columns)
    normalize = options.resize_mode != "none"

    cell_w = max(img.width for img in images)
    cell_h = max(img.height for img in images)
    rows = math.ceil(len(images) / columns)
    total_w = cell_w * columns + spacing * (columns - 1)
    total_h = cell_h * rows + spacing * (rows - 1)
    canvas = Image.new("RGBA", (max(1, total_w), max(1, total_h)), options.background)

    for idx, img in enumerate(images):
        row, col = divmod(idx, columns)
        cell_x = col * (cell_w + spacing)
        cell_y = row * (cell_h + spacing)
        rgba = img.convert("RGBA")
        placed = _fit_within(rgba, cell_w, cell_h) if normalize else rgba
        px = cell_x + (cell_w - placed.width) // 2
        py = cell_y + (cell_h - placed.height) // 2
        canvas.paste(placed, (px, py), placed)
    return canvas


def compose(images: list[Image.Image], options: StitchOptions) -> Image.Image:
    if not images:
        return Image.new("RGBA", (1, 1), options.background)
    if options.direction == "vertical":
        return compose_vertical(images, options)
    if options.direction == "grid":
        return compose_grid(images, options)
    return compose_horizontal(images, options)
