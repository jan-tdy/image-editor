"""PyView Editor - a PyQt6 image/video viewer and editor."""

from PIL import Image

# Pillow refuses to decode images above ~179 megapixels (DecompressionBombError)
# as a guard against malicious files. Stitched/stacked panoramas from this app's
# own Auto-Stack and Join Images features routinely exceed that, so the limit is
# raised rather than disabled outright - generous enough for real panoramas
# while still bounding worst-case memory use for a corrupt or hostile file.
Image.MAX_IMAGE_PIXELS = 1_000_000_000

__version__ = "0.3.0"
