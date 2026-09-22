"""Shared constants: supported file extensions and app metadata."""

APP_NAME = "PyView Editor"
APP_ORG = "JapySoft"

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp",
    ".tif", ".tiff", ".ico", ".ppm", ".pgm", ".pbm",
}

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg",
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

ZOOM_MIN = 0.02
ZOOM_MAX = 16.0
ZOOM_STEP = 1.25
