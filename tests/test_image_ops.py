import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_editor.core import image_ops


class ImageOpsTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (3, 2))
        self.image.putdata(
            [
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (255, 255, 0),
                (0, 255, 255),
                (255, 0, 255),
            ]
        )

    def test_rotate_90_in_both_directions_preserves_source(self):
        original = list(self.image.getdata())

        clockwise = image_ops.rotate90(self.image)
        counter_clockwise = image_ops.rotate90(self.image, clockwise=False)

        self.assertEqual(clockwise.size, (2, 3))
        self.assertEqual(clockwise.getpixel((1, 0)), (255, 0, 0))
        self.assertEqual(counter_clockwise.getpixel((0, 2)), (255, 0, 0))
        self.assertEqual(list(self.image.getdata()), original)

    def test_flip_operations_map_corner_pixels(self):
        self.assertEqual(image_ops.flip_horizontal(self.image).getpixel((2, 0)), (255, 0, 0))
        self.assertEqual(image_ops.flip_vertical(self.image).getpixel((0, 1)), (255, 0, 0))

    def test_crop_clamps_out_of_bounds_coordinates(self):
        cropped = image_ops.crop(self.image, (-20, -10, 50, 40))
        self.assertEqual(cropped.size, self.image.size)
        self.assertEqual(list(cropped.getdata()), list(self.image.getdata()))

    def test_crop_always_returns_at_least_one_pixel(self):
        cropped = image_ops.crop(self.image, (2, 1, 0, 0))
        self.assertEqual(cropped.size, (1, 1))
        self.assertEqual(cropped.getpixel((0, 0)), self.image.getpixel((2, 1)))

    def test_resize_with_aspect_ratio_does_not_upscale(self):
        self.assertEqual(image_ops.resize(self.image, (30, 20), keep_aspect=True).size, (3, 2))

    def test_exact_resize_uses_requested_dimensions(self):
        self.assertEqual(image_ops.resize(self.image, (6, 6), keep_aspect=False).size, (6, 6))

    def test_adjustment_values_are_clamped_to_slider_range(self):
        pixel = Image.new("RGB", (1, 1), (100, 50, 25))
        self.assertEqual(image_ops.apply_brightness(pixel, 500).getpixel((0, 0)), (200, 100, 50))
        self.assertEqual(image_ops.apply_brightness(pixel, -500).getpixel((0, 0)), (0, 0, 0))

    def test_zero_adjustments_return_the_original_object(self):
        self.assertIs(image_ops.apply_adjustments(self.image), self.image)

    def test_rgb_adjustment_changes_only_requested_channel_and_preserves_alpha(self):
        image = Image.new("RGBA", (1, 1), (100, 80, 60, 37))
        adjusted = image_ops.apply_rgb_channels(image, 100, 0, -50)
        self.assertEqual(adjusted.getpixel((0, 0)), (200, 80, 30, 37))

    def test_autocontrast_preserves_rgba_alpha_channel(self):
        image = Image.new("RGBA", (2, 1))
        image.putdata([(50, 50, 50, 12), (100, 100, 100, 231)])
        adjusted = image_ops.autocontrast(image, cutoff=0)
        self.assertEqual(list(adjusted.getchannel("A").getdata()), [12, 231])
        values = [adjusted.getpixel((x, 0))[0] for x in range(2)]
        self.assertEqual(values[0], 0)
        self.assertGreaterEqual(values[1], 254)

    def test_arbitrary_rotation_uses_transparent_fill_for_rgba(self):
        image = Image.new("RGBA", (4, 2), (255, 0, 0, 255))
        rotated = image_ops.rotate_arbitrary(image, 45)
        self.assertGreater(rotated.width, image.width)
        self.assertEqual(rotated.getpixel((0, 0))[3], 0)

    def test_load_with_orientation_applies_exif_rotation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oriented.jpg"
            image = Image.new("RGB", (2, 3), "red")
            exif = image.getexif()
            exif[274] = 6
            image.save(path, exif=exif)

            loaded = image_ops.load_with_orientation(str(path))

        self.assertEqual(loaded.size, (3, 2))
        self.assertIsNone(loaded.getexif().get(274))


if __name__ == "__main__":
    unittest.main()
