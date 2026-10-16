import unittest

import numpy as np
from PIL import Image

from image_editor.core.autostack_ops import (
    MODE_AUTO,
    AutoStackError,
    AutoStackOptions,
    downscale_for_stitch,
    stitch,
)


def noisy_image(size):
    """A random-noise image gives the feature detector real texture to
    match, unlike a solid color - closer to what real photos look like."""
    rng = np.random.default_rng(0)
    arr = (rng.random((size[1], size[0], 3)) * 255).astype("uint8")
    return Image.fromarray(arr, "RGB")


class DownscaleForStitchTests(unittest.TestCase):
    def test_leaves_small_images_untouched(self):
        image = Image.new("RGB", (100, 50))
        result = downscale_for_stitch(image, 2000)
        self.assertEqual(result.size, (100, 50))

    def test_zero_max_dim_means_no_cap(self):
        image = Image.new("RGB", (5000, 2000))
        result = downscale_for_stitch(image, 0)
        self.assertEqual(result.size, (5000, 2000))

    def test_shrinks_to_longest_side(self):
        image = Image.new("RGB", (4000, 2000))
        result = downscale_for_stitch(image, 1000)
        self.assertEqual(max(result.size), 1000)
        self.assertEqual(result.width / result.height, 2.0)


class StitchTests(unittest.TestCase):
    def test_requires_at_least_two_images(self):
        with self.assertRaises(AutoStackError):
            stitch([noisy_image((100, 100))], AutoStackOptions())

    def test_rejects_featureless_images_with_readable_error(self):
        a = Image.new("RGB", (200, 200), (128, 128, 128))
        b = Image.new("RGB", (200, 200), (128, 128, 128))
        with self.assertRaises(AutoStackError) as ctx:
            stitch([a, b], AutoStackOptions())
        self.assertTrue(str(ctx.exception))

    def test_combines_two_overlapping_crops_of_a_textured_scene(self):
        base = noisy_image((500, 300))
        left = base.crop((0, 0, 350, 300))
        right = base.crop((150, 0, 500, 300))
        result = stitch([left, right], AutoStackOptions(mode="flat"))
        # The combined image should cover roughly the full original width,
        # not just one of the two crops.
        self.assertGreater(result.image.width, 350)
        self.assertEqual(result.used_indices, [0, 1])
        self.assertEqual(result.used_count, 2)
        self.assertEqual(result.dropped_count, 0)

    def test_reports_photos_dropped_for_not_matching_anything(self):
        base = noisy_image((500, 300))
        left = base.crop((0, 0, 350, 300))
        right = base.crop((150, 0, 500, 300))
        unrelated = noisy_image((300, 300))  # different seed-independent noise, no overlap
        unrelated = Image.eval(unrelated, lambda p: 255 - p)  # make sure it differs from the rest

        result = stitch([left, right, unrelated], AutoStackOptions(mode="flat"))

        self.assertEqual(result.used_count, 2)
        self.assertEqual(result.dropped_count, 1)
        self.assertEqual(result.total_count, 3)
        self.assertNotIn(2, result.used_indices)

    def test_auto_mode_picks_whichever_candidate_uses_more_photos(self):
        base = noisy_image((500, 300))
        left = base.crop((0, 0, 350, 300))
        right = base.crop((150, 0, 500, 300))
        result = stitch([left, right], AutoStackOptions(mode=MODE_AUTO))
        self.assertEqual(result.used_count, 2)
        self.assertIn(result.mode_used, ("flat", "panorama"))


if __name__ == "__main__":
    unittest.main()
